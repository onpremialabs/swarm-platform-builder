"""El log por proyecto sobre `RedisBus` (SPEC-029 / T17.5 / AC2).

`test_project_log_stream.py` cubre `InProcessBus`, que es el camino por defecto.
Este cubre el otro: el que se usa con varios workers, donde los eventos viajan por
canales de Redis en vez de por colas en memoria. Es justo el camino en el que un
error de encaminamiento **no se vería en desarrollo** y sí en producción.

Se apoya en `fakeredis`, una implementación del protocolo con la que `redis-py`
habla de verdad: se ejercitan los `publish`/`subscribe` reales, los nombres de
canal y el vínculo artículo→proyecto. Lo que **no** cubre es el comportamiento de
un servidor Redis concreto ni la entrega entre procesos de sistema distintos.

`requirements-dev.txt` no lo instala la CI a propósito, así que allí se salta.
"""
import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

TEST_DB_PATH = (ROOT_DIR / "tests" / "test_project_log_stream_redis.db").resolve()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

fakeredis = pytest.importorskip(
    "fakeredis", reason="requiere fakeredis (requirements-dev.txt); la CI no lo instala")

from app.platform.bus import RedisBus  # noqa: E402


@pytest.fixture
def bus(monkeypatch):
    """Un `RedisBus` cuyo cliente es un Redis en memoria, no un stub nuestro.

    Se sustituye el cliente y no el bus: así se recorre el código de
    `RedisBus` tal cual —sus canales, su buzón de salida, su puente de pubsub—.
    """
    import fakeredis.aioredis as fake

    servidor = fakeredis.FakeServer()

    class _BusDePrueba(RedisBus):
        def __init__(self):
            # Se salta el __init__ de RedisBus para no abrir una conexión real,
            # pero se conserva todo su estado.
            from app.platform.bus import InProcessBus
            InProcessBus.__init__(self)
            self._redis = fake.FakeRedis(server=servidor, decode_responses=True)
            self._control_subs = {}
            self._outbox = asyncio.Queue()
            self._drain_task = None

    return _BusDePrueba()


async def _drenar(cola, intentos=40):
    """Lo que llegue a la cola, dando tiempo al puente de pubsub."""
    recibidos = []
    for _ in range(intentos):
        try:
            recibidos.append(await asyncio.wait_for(cola.get(), timeout=0.05))
        except asyncio.TimeoutError:
            if recibidos:
                return recibidos
    return recibidos


@pytest.mark.asyncio
async def test_el_evento_llega_al_canal_del_proyecto(bus):
    """El camino completo: vincular, publicar y recibir por el canal del proyecto."""
    proyecto, articulo = uuid.uuid4(), uuid.uuid4()
    bus.bind_project(articulo, proyecto)
    await asyncio.sleep(0.05)  # el vínculo se escribe en una tarea aparte

    async with bus.subscribe_project(proyecto) as cola:
        await asyncio.sleep(0.05)  # que el puente se suscriba antes de publicar
        await bus.publish(articulo, {"type": "log", "message": "hola"})
        recibidos = await _drenar(cola)

    assert recibidos, "el evento no llegó por el canal del proyecto"
    assert recibidos[0]["message"] == "hola"
    assert recibidos[0]["article_id"] == str(articulo)


@pytest.mark.asyncio
async def test_no_se_filtra_entre_proyectos_sobre_redis(bus):
    """AC2 en el camino de varios workers: cada proyecto tiene su canal."""
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    art1, art2 = uuid.uuid4(), uuid.uuid4()
    bus.bind_project(art1, p1)
    bus.bind_project(art2, p2)
    await asyncio.sleep(0.05)

    async with bus.subscribe_project(p1) as cola1:
        await asyncio.sleep(0.05)
        await bus.publish(art2, {"type": "log", "message": "del proyecto 2"})
        await bus.publish(art1, {"type": "log", "message": "del proyecto 1"})
        recibidos = await _drenar(cola1)

    mensajes = [e["message"] for e in recibidos]
    assert "del proyecto 1" in mensajes
    assert "del proyecto 2" not in mensajes, "se filtró un evento de otro proyecto"


@pytest.mark.asyncio
async def test_un_articulo_sin_vincular_no_llega_a_ningun_proyecto(bus):
    """Fallar cerrado también aquí: sin vínculo no se encamina."""
    proyecto, huerfano = uuid.uuid4(), uuid.uuid4()

    async with bus.subscribe_project(proyecto) as cola:
        await asyncio.sleep(0.05)
        await bus.publish(huerfano, {"type": "log", "message": "sin proyecto"})
        assert await _drenar(cola, intentos=6) == []


@pytest.mark.asyncio
async def test_el_vinculo_se_guarda_en_redis_para_otros_workers(bus):
    """El worker que atiende el log puede no ser el que ejecuta.

    Por eso el vínculo artículo→proyecto va a Redis y no solo a memoria: si
    viviera únicamente en el proceso que ejecuta, el que sirve el log no sabría
    a qué canal encaminar y el flujo saldría vacío.
    """
    from app.platform.bus import _ARTICLE_PROJECT

    proyecto, articulo = uuid.uuid4(), uuid.uuid4()
    bus.bind_project(articulo, proyecto)
    await asyncio.sleep(0.05)

    guardado = await bus._redis.get(_ARTICLE_PROJECT.format(article_id=articulo))
    assert guardado == str(proyecto)

    # Y se resuelve desde Redis aunque el proceso no lo tenga en memoria.
    bus._article_project.clear()
    async with bus.subscribe_project(proyecto) as cola:
        await asyncio.sleep(0.05)
        await bus.publish(articulo, {"type": "log", "message": "desde otro worker"})
        recibidos = await _drenar(cola)

    assert recibidos, "sin el vínculo en Redis, otro worker no encamina el evento"
    assert recibidos[0]["message"] == "desde otro worker"


@pytest.mark.asyncio
async def test_el_canal_por_articulo_sigue_funcionando(bus):
    """El reparto al proyecto no puede romper el stream que ya existía."""
    proyecto, articulo = uuid.uuid4(), uuid.uuid4()
    bus.bind_project(articulo, proyecto)
    await asyncio.sleep(0.05)

    async with bus.subscribe(articulo) as cola:
        await asyncio.sleep(0.05)
        await bus.publish(articulo, {"type": "token", "text": "hola"})
        recibidos = await _drenar(cola)

    assert recibidos, "el stream por artículo dejó de recibir"
    assert recibidos[0]["text"] == "hola"
