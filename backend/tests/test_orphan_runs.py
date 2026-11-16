"""Pasos que se quedan abiertos y hacen que un agente salga «incierto» (T16.4).

El estado «incierto» es correcto cuando de verdad no se sabe. El problema es que
había dos formas de llegar a él sin que nada estuviera pasando:

1. **Cancelar una ejecución.** `asyncio.CancelledError` hereda de `BaseException`,
   no de `Exception`, así que el `except Exception` del wrapper no la veía y
   `log_run_end` no llegaba a ejecutarse. Cancelar es una acción normal de la
   interfaz: el caso no era raro, era uno por cada cancelación.
2. **Un proceso que muere de golpe.** Eso no se puede cerrar desde dentro, así que
   se barre al arrancar.
"""
import asyncio
import datetime
import inspect
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

TEST_DB_PATH = (ROOT_DIR / "tests" / "test_orphan_runs.db").resolve()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.models.agent_run import AgentRunModel  # noqa: E402
from app.modules.agents.application import use_cases  # noqa: E402
from app.platform.summary import SWARM_STALE_AFTER_S  # noqa: E402


@pytest_asyncio.fixture
async def esquema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def _abrir(agente: str, hace_segundos: int) -> None:
    """Deja una fila como la que escribe `log_run_start`, sin cerrar."""
    async with AsyncSessionLocal() as s:
        s.add(AgentRunModel(
            agent_name=agente,
            status="running",
            started_at=datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(seconds=hace_segundos),
        ))
        await s.commit()


async def _estados() -> dict:
    async with AsyncSessionLocal() as s:
        filas = (await s.execute(select(AgentRunModel))).scalars().all()
        return {f.agent_name: (f.status, f.finished_at is not None) for f in filas}


# ── 1. La cancelación cierra su paso ────────────────────────────────────────

def test_el_wrapper_captura_cancelled_error():
    """`CancelledError` no es `Exception`: necesita su propia rama.

    Si alguien quita esta rama, cancelar vuelve a dejar la fila abierta y el
    agente vuelve a quedarse en «incierto» para siempre.
    """
    fuente = inspect.getsource(use_cases.make_node_wrapper)
    assert "except asyncio.CancelledError" in fuente, (
        "sin esta rama, cancelar deja el paso abierto para siempre"
    )


def test_la_cancelacion_cierra_el_run_y_lo_traza():
    fuente = inspect.getsource(use_cases.make_node_wrapper)
    rama = fuente.split("except asyncio.CancelledError")[1].split("except Exception")[0]

    assert "log_run_end" in rama, "la fila de agent_runs tiene que cerrarse"
    assert "cancelled" in rama
    assert "log_run_step" in rama, "la traza registra el paso cancelado (T9.1/AC1)"


def test_la_cancelacion_se_vuelve_a_lanzar():
    """Tragarse una cancelación deja la tarea viva: peor que el problema."""
    fuente = inspect.getsource(use_cases.make_node_wrapper)
    rama = fuente.split("except asyncio.CancelledError")[1].split("except Exception")[0]
    assert "raise" in rama


# ── 2. La barrida al arrancar ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cierra_los_pasos_viejos_que_quedaron_abiertos(esquema):
    await _abrir("redactor", hace_segundos=SWARM_STALE_AFTER_S + 600)

    cerrados = await use_cases.close_orphan_runs()

    assert cerrados == 1
    estado, tiene_fin = (await _estados())["redactor"]
    assert estado == "interrupted"
    assert tiene_fin, "tiene que quedar con finished_at para no salir como abierto"


@pytest.mark.asyncio
async def test_no_toca_un_paso_recien_abierto(esquema):
    """Uno de hace 30 s puede estar ejecutándose de verdad.

    Cerrarlo sería peor que el problema: convertiría una ejecución viva en una
    interrumpida en el registro.
    """
    await _abrir("investigador", hace_segundos=30)

    cerrados = await use_cases.close_orphan_runs()

    assert cerrados == 0
    estado, tiene_fin = (await _estados())["investigador"]
    assert estado == "running" and not tiene_fin


@pytest.mark.asyncio
async def test_usa_el_mismo_umbral_que_la_portada(esquema):
    """Dos criterios distintos para la misma pregunta acabarían discrepando.

    Si la barrida cerrara antes que el umbral de «incierto», habría una ventana
    donde la portada dice una cosa y el registro otra.
    """
    await _abrir("revisor", hace_segundos=SWARM_STALE_AFTER_S - 60)
    assert await use_cases.close_orphan_runs() == 0

    await _abrir("formateador", hace_segundos=SWARM_STALE_AFTER_S + 60)
    assert await use_cases.close_orphan_runs() == 1


@pytest.mark.asyncio
async def test_no_toca_los_que_ya_estaban_cerrados(esquema):
    async with AsyncSessionLocal() as s:
        s.add(AgentRunModel(
            agent_name="publicador", status="completed",
            started_at=datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(seconds=SWARM_STALE_AFTER_S + 600),
            finished_at=datetime.datetime.now(datetime.timezone.utc),
        ))
        await s.commit()

    assert await use_cases.close_orphan_runs() == 0
    assert (await _estados())["publicador"][0] == "completed"


@pytest.mark.asyncio
async def test_sin_huerfanos_no_hace_nada(esquema):
    assert await use_cases.close_orphan_runs() == 0


@pytest.mark.asyncio
async def test_se_llama_al_arrancar():
    """De nada sirve la función si nadie la invoca."""
    import app.main as main

    assert "close_orphan_runs" in inspect.getsource(main.lifespan)
