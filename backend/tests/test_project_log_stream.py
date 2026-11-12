"""Log en vivo por proyecto, filtrado en servidor (SPEC-029 / T17.5 / AC2).

El riesgo que la spec marca como principal es la fuga entre proyectos: el SSE
existente es por artículo y hereda su autorización, pero un flujo «del proyecto»
puede entregar de más si filtra en el cliente. Aquí se comprueba lo contrario:
un evento de otro proyecto **no sale del servidor**.
"""
import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

TEST_DB_PATH = (ROOT_DIR / "tests" / "test_project_log_stream.db").resolve()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

from app.platform.bus import InProcessBus  # noqa: E402


async def _drenar(cola) -> list:
    """Todo lo que haya ya en la cola, sin quedarse esperando."""
    recibidos = []
    while True:
        try:
            recibidos.append(await asyncio.wait_for(cola.get(), timeout=0.05))
        except asyncio.TimeoutError:
            return recibidos


@pytest.mark.asyncio
async def test_el_flujo_de_un_proyecto_no_recibe_del_otro():
    """AC2: ni siquiera llega al cliente para ser filtrado en el navegador."""
    bus = InProcessBus()
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    art_p1, art_p2 = uuid.uuid4(), uuid.uuid4()

    bus.bind_project(art_p1, p1)
    bus.bind_project(art_p2, p2)

    async with bus.subscribe_project(p1) as cola1:
        bus.publish_nowait(art_p1, {"type": "log", "message": "del proyecto 1"})
        bus.publish_nowait(art_p2, {"type": "log", "message": "del proyecto 2"})

        recibidos = await _drenar(cola1)

    mensajes = [e["message"] for e in recibidos]
    assert "del proyecto 1" in mensajes
    assert "del proyecto 2" not in mensajes, "se filtró un evento de otro proyecto"
    assert len(recibidos) == 1


@pytest.mark.asyncio
async def test_el_evento_del_proyecto_dice_de_que_articulo_viene():
    """El flujo mezcla ejecuciones: sin `article_id` no se podrían separar."""
    bus = InProcessBus()
    proyecto, articulo = uuid.uuid4(), uuid.uuid4()
    bus.bind_project(articulo, proyecto)

    async with bus.subscribe_project(proyecto) as cola:
        bus.publish_nowait(articulo, {"type": "agent_start", "agent": "redactor"})
        recibidos = await _drenar(cola)

    assert recibidos[0]["article_id"] == str(articulo)
    assert recibidos[0]["agent"] == "redactor"


@pytest.mark.asyncio
async def test_un_articulo_sin_vincular_no_emite_en_ningun_proyecto():
    """Ante la duda no se entrega: fallar cerrado, no abierto."""
    bus = InProcessBus()
    proyecto, huerfano = uuid.uuid4(), uuid.uuid4()

    async with bus.subscribe_project(proyecto) as cola:
        bus.publish_nowait(huerfano, {"type": "log", "message": "sin proyecto"})
        assert await _drenar(cola) == []


@pytest.mark.asyncio
async def test_el_stream_por_articulo_sigue_funcionando():
    """El fan-out al proyecto no puede romper la suscripción que ya existía."""
    bus = InProcessBus()
    proyecto, articulo = uuid.uuid4(), uuid.uuid4()
    bus.bind_project(articulo, proyecto)

    async with bus.subscribe(articulo) as cola_art:
        bus.publish_nowait(articulo, {"type": "token", "text": "hola"})
        recibidos = await _drenar(cola_art)

    assert len(recibidos) == 1
    assert recibidos[0]["text"] == "hola"
    # El evento del artículo no se enriquece: ese flujo ya sabe de qué artículo es.
    assert "article_id" not in recibidos[0]


@pytest.mark.asyncio
async def test_desvincular_corta_la_entrega_al_proyecto():
    bus = InProcessBus()
    proyecto, articulo = uuid.uuid4(), uuid.uuid4()
    bus.bind_project(articulo, proyecto)
    bus.unbind_project(articulo)

    async with bus.subscribe_project(proyecto) as cola:
        bus.publish_nowait(articulo, {"type": "log", "message": "ya no"})
        assert await _drenar(cola) == []


@pytest.mark.asyncio
async def test_dos_oyentes_del_mismo_proyecto_reciben_los_dos():
    bus = InProcessBus()
    proyecto, articulo = uuid.uuid4(), uuid.uuid4()
    bus.bind_project(articulo, proyecto)

    async with bus.subscribe_project(proyecto) as a, bus.subscribe_project(proyecto) as b:
        bus.publish_nowait(articulo, {"type": "log", "message": "a los dos"})
        assert len(await _drenar(a)) == 1
        assert len(await _drenar(b)) == 1
