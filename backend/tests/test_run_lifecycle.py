import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from test_explain_endpoint import db, _usuario, _articulo
from app.core.database import AsyncSessionLocal
from app.models import AgentRunModel, AgentRunStepModel
from app.platform import run_lifecycle as life
from app.modules.agents.application import use_cases as uc


@pytest.fixture
def owner(tmp_path, monkeypatch):
    instance = life.RuntimeOwner(tmp_path / "owners")
    monkeypatch.setattr(life, "runtime_owner", instance)
    monkeypatch.setattr(uc, "runtime_owner", instance)
    yield instance
    instance.release()


@pytest_asyncio.fixture
async def article(db):
    user = await _usuario("lifecycle@test.com")
    return await _articulo(user.id)


def state(article):
    return {"article_id":article.id,"author_id":article.author_id,"title":"test",
            "current_step_index":0,"loop_count":0,"agent_settings":{}}


async def rows(article):
    async with AsyncSessionLocal() as session:
        runs = list((await session.execute(select(AgentRunModel).where(AgentRunModel.article_id==article.id))).scalars())
        steps = list((await session.execute(select(AgentRunStepModel).where(AgentRunStepModel.article_id==article.id))).scalars())
        return runs, steps


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False,True])
async def test_normal_and_failed_attempts_are_closed(article, owner, fails):
    async def agent(data):
        if fails:
            raise ValueError("real failure")
        return {"draft_text":"done"}
    wrapper = uc.make_node_wrapper("redactor", agent)
    if fails:
        with pytest.raises(ValueError):
            await wrapper(state(article))
    else:
        await wrapper(state(article))
    runs, steps = await rows(article)
    assert len(runs)==len(steps)==1
    assert runs[0].status == steps[0].status == ("failed" if fails else "completed")
    assert runs[0].finished_at is not None
    assert runs[0].input_payload[life.OWNER_KEY]["id"] == owner.id
    assert owner.tasks == owner.terminal_results == {}


@pytest.mark.asyncio
async def test_cancel_closes_run_and_trace_and_propagates_cancellation(article, owner):
    started=asyncio.Event()
    async def agent(data):
        started.set()
        await asyncio.Event().wait()
    task=asyncio.create_task(uc.make_node_wrapper("redactor",agent)(state(article)))
    await asyncio.wait_for(started.wait(),5)
    assert await life.reconcile_orphan_runs(owner)==0
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    runs, steps=await rows(article)
    assert runs[0].status == steps[0].status == "cancelled"
    assert runs[0].finished_at is not None
    assert not owner.tasks


@pytest.mark.asyncio
async def test_preparation_exception_also_closes_run(article, owner, monkeypatch):
    def broken(*args):
        raise ValueError("invalid agent parameters")
    monkeypatch.setattr(uc.explainability,"params_of",broken)
    async def unused(data):
        pytest.fail("agent must not start")
    with pytest.raises(ValueError):
        await uc.make_node_wrapper("redactor",unused)(state(article))
    runs, steps=await rows(article)
    assert runs[0].status == steps[0].status == "failed"
    assert runs[0].finished_at is not None
    assert not owner.tasks


@pytest.mark.asyncio
async def test_close_retries_and_does_not_overwrite_terminal_result(article, owner, monkeypatch):
    run_id=await uc.log_run_start("redactor",article.id,article.author_id,{})
    factory=uc.AsyncSessionLocal
    attempts=0
    def temporary_failure():
        nonlocal attempts
        attempts+=1
        if attempts<3:
            raise RuntimeError("temporary storage failure")
        return factory()
    monkeypatch.setattr(uc,"AsyncSessionLocal",temporary_failure)
    await uc.log_run_end(run_id,{"draft_text":"actual output"},"completed")
    assert attempts==3
    await uc.log_run_end(run_id,{},"failed", "late cleanup")
    runs,_=await rows(article)
    assert runs[0].status=="completed"
    assert runs[0].output_payload=={"draft_text":"actual output"}
    assert runs[0].error_message is None


@pytest.mark.asyncio
async def test_monitor_preserves_pending_success_after_database_outage(article,owner,monkeypatch):
    factory=uc.AsyncSessionLocal
    async def attempt():
        run_id=await uc.log_run_start("redactor",article.id,article.author_id,{})
        def broken():
            raise RuntimeError("database temporarily unavailable")
        monkeypatch.setattr(uc,"AsyncSessionLocal",broken)
        await uc.log_run_end(run_id,{"draft_text":"saved later"},"completed")
        return run_id
    run_id=await asyncio.create_task(attempt())
    monkeypatch.setattr(uc,"AsyncSessionLocal",factory)
    assert run_id in owner.terminal_results
    assert await life.reconcile_orphan_runs(owner)==1
    runs,_=await rows(article)
    assert runs[0].status=="completed"
    assert runs[0].output_payload=={"draft_text":"saved later"}
    assert not owner.tasks and not owner.terminal_results


@pytest.mark.asyncio
async def test_live_worker_survives_reconciliation_and_dead_worker_closes(article,owner):
    other=life.RuntimeOwner(owner.directory)
    metadata=other.metadata
    try:
        async with AsyncSessionLocal() as session:
            session.add(AgentRunModel(agent_name="investigador",article_id=article.id,
                author_id=article.author_id,input_payload={life.OWNER_KEY:metadata}))
            await session.commit()
        assert await life.reconcile_orphan_runs(owner)==0
        other.release()
        assert await life.reconcile_orphan_runs(owner)==1
        assert await life.reconcile_orphan_runs(owner)==0
        runs,_=await rows(article)
        assert runs[0].status=="interrupted" and runs[0].finished_at is not None
    finally:
        other.release()


@pytest.mark.asyncio
async def test_force_kill_of_test_worker_releases_os_lock(article,owner):
    code = "import sys,json,os; from app.platform.run_lifecycle import RuntimeOwner; o=RuntimeOwner(sys.argv[1]); print(json.dumps(o.metadata),flush=True); sys.stdin.read(1); os._exit(7)"
    process=subprocess.Popen([sys.executable,"-c",code,str(owner.directory)],
        cwd=Path(__file__).resolve().parents[1],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    try:
        metadata=json.loads(process.stdout.readline())
        async with AsyncSessionLocal() as session:
            session.add(AgentRunModel(agent_name="redactor",article_id=article.id,
                author_id=article.author_id,input_payload={life.OWNER_KEY:metadata}))
            await session.commit()
        assert await life.reconcile_orphan_runs(owner)==0
        process.stdin.write("x")  # os._exit: bypass all Python cleanup in the actual worker.
        process.stdin.flush()
        process.wait(timeout=5)
        assert await life.reconcile_orphan_runs(owner)==1
        runs,_=await rows(article)
        assert runs[0].status=="interrupted" and runs[0].finished_at is not None
    finally:
        if process.poll() is None:
            process.stdin.close()  # EOF also releases the test worker.
            process.wait(timeout=5)
        else:
            process.stdin.close()
        process.stdout.close()


@pytest.mark.asyncio
async def test_unknown_legacy_and_other_host_are_not_closed_without_evidence(article,owner):
    async with AsyncSessionLocal() as session:
        for payload in ({}, {life.OWNER_KEY:{"host":"another-server","id":owner.id}}):
            session.add(AgentRunModel(agent_name="redactor",article_id=article.id,
                author_id=article.author_id,input_payload=payload))
        await session.commit()
    assert await life.reconcile_orphan_runs(owner)==0


@pytest.mark.asyncio
async def test_shutdown_cancels_task_closes_record_and_releases_lock(article,owner):
    started=asyncio.Event()
    async def agent(data):
        started.set()
        await asyncio.Event().wait()
    task=asyncio.create_task(uc.make_node_wrapper("redactor",agent)(state(article)))
    await asyncio.wait_for(started.wait(),5)
    monitor=asyncio.create_task(asyncio.Event().wait())
    await life.stop_run_lifecycle(monitor,[task])
    assert task.done() and task.cancelled()
    assert monitor.done()
    runs,steps=await rows(article)
    assert runs[0].status==steps[0].status=="cancelled"
    assert runs[0].finished_at is not None
    assert not owner.tasks and owner.file is None
