"""Close abandoned run records without confusing them with active workers.

A process holds an OS file lock for its lifetime. The lock is released even on
forced termination. Ownership is stored in the existing run input metadata;
no heartbeat timeout can incorrectly close a long LLM call or a human pause.
"""
import asyncio
import logging
import os
import socket
import uuid
from pathlib import Path

from sqlalchemy import select, update
from datetime import datetime, timezone
from app.core.database import AsyncSessionLocal
from app.models.agent_run import AgentRunModel

logger = logging.getLogger(__name__)
OWNER_KEY = "_runtime_owner"
HOST = socket.gethostname()
LOCK_DIR = Path(__file__).resolve().parents[2] / "data" / "runtime-owners"


def _lock(file):
    file.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


class RuntimeOwner:
    def __init__(self, directory=LOCK_DIR):
        self.id = str(uuid.uuid4())
        self.directory = Path(directory)
        self.file = None
        self.tasks = {}
        self.terminal_results = {}

    @property
    def metadata(self):
        self.acquire()
        return {"id": self.id, "host": HOST, "pid": os.getpid()}

    def acquire(self):
        if self.file is not None:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        file = (self.directory / f"{self.id}.lock").open("a+b")
        try:
            file.write(b"0")
            file.flush()
            _lock(file)
        except BaseException:
            file.close()
            raise
        self.file = file

    def release(self):
        if self.file is not None:
            self.file.close()  # OS releases the lock, including on process death.
            self.file = None
            (self.directory / f"{self.id}.lock").unlink(missing_ok=True)

    def is_dead(self, metadata):
        if not isinstance(metadata, dict) or metadata.get("host") != HOST:
            return False  # Legacy or another host: no evidence of abandonment.
        try:
            owner_id = str(uuid.UUID(metadata["id"]))
        except (KeyError, ValueError, TypeError):
            return False
        if owner_id == self.id:
            return False
        path = self.directory / f"{owner_id}.lock"
        if not path.exists():
            return True
        try:
            with path.open("r+b") as file:
                _lock(file)
            return True
        except (OSError, BlockingIOError):
            return False


runtime_owner = RuntimeOwner()


async def reconcile_orphan_runs(owner=None):
    owner = owner or runtime_owner
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(AgentRunModel).where(
            AgentRunModel.status == "running", AgentRunModel.finished_at.is_(None),
        ))).scalars().all()
        closed = 0
        dead_files = set()
        for row in rows:
            metadata = (row.input_payload or {}).get(OWNER_KEY)
            own = isinstance(metadata, dict) and metadata.get("host") == HOST and metadata.get("id") == owner.id
            task = owner.tasks.get(row.run_id) if own else None
            abandoned = (own and (task is None or task.done())) or owner.is_dead(metadata)
            if not abandoned:
                continue
            values = {"status": "interrupted", "error_message":
                "Intento cerrado automáticamente: terminó su tarea o el proceso responsable. La fecha de cierre es la de conciliación."}
            if own and row.run_id in owner.terminal_results:
                values = owner.terminal_results[row.run_id]
            result = await session.execute(update(AgentRunModel).where(
                AgentRunModel.run_id == row.run_id, AgentRunModel.status == "running",
                AgentRunModel.finished_at.is_(None),
            ).values(**values, finished_at=datetime.now(timezone.utc)))
            closed += result.rowcount
            if not own:
                dead_files.add(str(uuid.UUID(metadata["id"])))
        await session.commit()
        # Only discard retry metadata after the database transaction succeeds.
        for run_id, task in list(owner.tasks.items()):
            if task is None or task.done():
                owner.tasks.pop(run_id, None)
                owner.terminal_results.pop(run_id, None)
        for owner_id in dead_files:
            (owner.directory / f"{owner_id}.lock").unlink(missing_ok=True)
        if closed:
            logger.warning("Closed %s abandoned agent run records", closed)
        return closed


async def _monitor():
    while True:
        await asyncio.sleep(15)
        try:
            await reconcile_orphan_runs()
        except Exception:
            logger.exception("Could not reconcile agent run records; retrying next cycle")


async def start_run_lifecycle():
    runtime_owner.acquire()
    try:
        await reconcile_orphan_runs()
    except Exception:
        runtime_owner.release()
        raise
    return asyncio.create_task(_monitor(), name="run-record-reconciliation")


async def stop_run_lifecycle(monitor, pipeline_tasks):
    monitor.cancel()
    await asyncio.gather(monitor, return_exceptions=True)
    tasks = {task for task in pipeline_tasks if not task.done() and task is not asyncio.current_task()}
    for task in tasks:
        task.cancel()
    if tasks:
        _, pending = await asyncio.wait(tasks, timeout=10)
    else:
        pending = set()
    try:
        await reconcile_orphan_runs()
    except Exception:
        logger.exception("Could not close abandoned run records at shutdown")
    if not pending:
        runtime_owner.release()
    else:
        # Keep ownership until the process exits; another worker must not claim
        # a still-live coroutine has already died.
        logger.error("%s cancelled pipeline tasks did not finish before shutdown", len(pending))
