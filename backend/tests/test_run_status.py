"""Saber qué se está ejecutando, desde el servidor (SPEC-030 / T18.7).

La vista en vivo se construía con lo que el Flow Designer pasaba en el estado de
navegación. Eso se pierde al cambiar de pestaña o al recargar, y la página caía en
modo histórico **aunque el pipeline siguiera corriendo**. El servidor sabía que
había algo en marcha —`is_running`— pero no podía decir **qué**.
"""
import sys
import uuid
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.platform.bus import InProcessBus  # noqa: E402


@pytest.mark.asyncio
async def test_la_marca_guarda_con_que_se_ejecuta():
    bus = InProcessBus()
    art = uuid.uuid4()
    await bus.mark_running(art, {"flow_sequence": ["redactor", "revisor"],
                                 "project_id": "p-1"})

    info = await bus.get_run_info(art)
    assert info["flow_sequence"] == ["redactor", "revisor"]
    assert await bus.is_running(art) is True


@pytest.mark.asyncio
async def test_sin_ejecucion_no_hay_info():
    bus = InProcessBus()
    assert await bus.get_run_info(uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_el_agente_actual_se_actualiza_sin_pisar_el_resto():
    bus = InProcessBus()
    art = uuid.uuid4()
    await bus.mark_running(art, {"flow_sequence": ["a", "b"], "project_id": "p-1"})

    await bus.update_run_info(art, current_agent="b")

    info = await bus.get_run_info(art)
    assert info["current_agent"] == "b"
    assert info["flow_sequence"] == ["a", "b"], "no puede perderse al actualizar"
    assert info["project_id"] == "p-1"


@pytest.mark.asyncio
async def test_actualizar_algo_ya_terminado_no_lo_resucita():
    """Una carrera entre el cierre y un último evento no debe reabrir la marca."""
    bus = InProcessBus()
    art = uuid.uuid4()
    await bus.mark_running(art, {"flow_sequence": ["a"]})
    await bus.clear_running(art)

    await bus.update_run_info(art, current_agent="a")

    assert await bus.is_running(art) is False
    assert await bus.get_run_info(art) is None


@pytest.mark.asyncio
async def test_al_terminar_deja_de_aparecer():
    bus = InProcessBus()
    art = uuid.uuid4()
    await bus.mark_running(art, {"flow_sequence": ["a"]})
    assert len(await bus.running_articles()) == 1

    await bus.clear_running(art)
    assert await bus.running_articles() == {}


@pytest.mark.asyncio
async def test_la_info_devuelta_es_una_copia():
    """Quien la lea no puede modificar el estado del bus sin querer."""
    bus = InProcessBus()
    art = uuid.uuid4()
    await bus.mark_running(art, {"flow_sequence": ["a"]})

    info = await bus.get_run_info(art)
    info["flow_sequence"].append("intruso")

    assert (await bus.get_run_info(art))["flow_sequence"] == ["a"]


def test_el_endpoint_por_articulo_existe():
    from app.main import app
    assert "/api/v1/agents/{article_id}/status" in app.openapi()["paths"]


def test_el_endpoint_del_proyecto_existe():
    from app.main import app
    assert "/api/v1/dashboard/running" in app.openapi()["paths"]


def test_el_listado_del_proyecto_filtra_por_proyecto():
    """El aislamiento de T8.5 también aquí: y una marca sin proyecto se descarta.

    No se puede comprobar a quién pertenece, así que no se enseña. El aislamiento
    no admite suposiciones.
    """
    import inspect
    from app.routers import dashboard

    fuente = inspect.getsource(dashboard.running_in_project)
    assert 'info.get("project_id") == str(project.project_id)' in fuente
