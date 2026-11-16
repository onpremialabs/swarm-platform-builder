"""Cancelar una generación libera el modelo de Ollama (#509).

Cada agente pide `keep_alive=0`, pero Ollama lo aplica **al terminar la
petición**: una generación cancelada a mitad de stream la abandona y el modelo se
queda cargado con el keep-alive por defecto. En equipos con VRAM justa eso deja la
máquina inservible para la siguiente ejecución.

- AC2/AC5: al cancelar se pide la descarga **explícitamente** (`/api/generate`,
  prompt vacío, `keep_alive: 0`) del modelo que resolvió el agente cancelado.
- AC3: si la descarga falla, se registra con su motivo y la cancelación se
  completa igual.
- AC4: con un proveedor remoto no se intenta descargar nada.
"""
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

TEST_DB_PATH = (ROOT_DIR / "tests" / "test_cancel_unload.db").resolve()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

from sqlalchemy import select  # noqa: E402

from app.core import config  # noqa: E402
from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.models import AgentRunStepModel  # noqa: E402
from app.modules.agents.adapters import redactor as adapter_redactor  # noqa: E402
from app.modules.agents.application import use_cases as orquestador  # noqa: E402
from app.platform import llm  # noqa: E402


# ── unload_model: la petición a Ollama ──────────────────────────────────────

def _cliente_falso(monkeypatch, handler):
    """Sustituye el cliente HTTP del dispatcher por uno con transporte simulado."""
    peticiones = []
    original = httpx.AsyncClient

    def _handler(request):
        peticiones.append(request)
        return handler(request)

    def _fabrica(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_handler)
        return original(*args, **kwargs)

    monkeypatch.setattr(llm.httpx, "AsyncClient", _fabrica)
    return peticiones


@pytest.mark.asyncio
async def test_unload_pide_keep_alive_cero_con_prompt_vacio(monkeypatch):
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "ollama", raising=False)
    monkeypatch.setattr(config.settings, "OLLAMA_BASE_URL", "http://ollama.test:11434", raising=False)
    peticiones = _cliente_falso(monkeypatch, lambda r: httpx.Response(200, json={"done": True}))

    assert await llm.unload_model("qwen3.5:9b") is True

    assert len(peticiones) == 1
    peticion = peticiones[0]
    assert peticion.method == "POST"
    assert str(peticion.url) == "http://ollama.test:11434/api/generate"
    cuerpo = json.loads(peticion.content)
    assert cuerpo["model"] == "qwen3.5:9b"
    assert cuerpo["prompt"] == ""
    assert cuerpo["keep_alive"] == 0


@pytest.mark.parametrize("proveedor", ["anthropic", "openai", "Anthropic"])
@pytest.mark.asyncio
async def test_unload_no_hace_nada_con_un_proveedor_remoto(monkeypatch, proveedor):
    """AC4: no hay modelo local que liberar."""
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", proveedor, raising=False)
    peticiones = _cliente_falso(monkeypatch, lambda r: httpx.Response(200, json={}))

    assert await llm.unload_model("claude-sonnet-4") is False
    assert peticiones == []


@pytest.mark.asyncio
async def test_unload_sin_modelo_no_llama(monkeypatch):
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "ollama", raising=False)
    peticiones = _cliente_falso(monkeypatch, lambda r: httpx.Response(200, json={}))
    assert await llm.unload_model(None) is False
    assert await llm.unload_model("") is False
    assert peticiones == []


@pytest.mark.asyncio
async def test_unload_que_falla_por_red_no_lanza_y_deja_motivo(monkeypatch, caplog):
    """AC3: mejor-esfuerzo, con el motivo en el log."""
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "ollama", raising=False)

    def _caido(request):
        raise httpx.ConnectError("All connection attempts failed", request=request)

    _cliente_falso(monkeypatch, _caido)
    with caplog.at_level(logging.WARNING, logger="app.platform.llm"):
        assert await llm.unload_model("qwen3.5:9b") is False
    assert "qwen3.5:9b" in caplog.text
    assert "All connection attempts failed" in caplog.text


@pytest.mark.asyncio
async def test_unload_con_respuesta_de_error_no_lanza_y_deja_motivo(monkeypatch, caplog):
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "ollama", raising=False)
    _cliente_falso(monkeypatch, lambda r: httpx.Response(404, text="model not found"))
    with caplog.at_level(logging.WARNING, logger="app.platform.llm"):
        assert await llm.unload_model("inexistente") is False
    assert "404" in caplog.text and "model not found" in caplog.text


# ── De extremo a extremo: cancelar el pipeline pide la descarga ─────────────

@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def runs(monkeypatch):
    """Registra cómo se cierra cada `agent_run`."""
    cierres = []

    async def _start(agent_name, article_id, author_id, input_payload):
        return uuid.uuid4()

    async def _end(run_id, output_payload, status, error_message=None):
        cierres.append(status)

    monkeypatch.setattr(orquestador, "log_run_start", _start)
    monkeypatch.setattr(orquestador, "log_run_end", _end)
    return cierres


@pytest.fixture
def redactor_colgado(monkeypatch):
    """Un redactor que se queda generando hasta que lo cancelan."""
    empezado = asyncio.Event()

    async def redactor(state):
        empezado.set()
        await asyncio.sleep(3600)
        return {"draft_text": "nunca"}

    monkeypatch.setattr(adapter_redactor, "run_redactor", redactor)
    return empezado


async def _lanzar_y_cancelar(empezado):
    article_id = uuid.uuid4()
    tarea = asyncio.create_task(orquestador.Orchestrator.run(
        article_id=article_id, author_id=uuid.uuid4(), title="T", keywords=[],
        scientific_format="apa", flow_sequence=["redactor"],
    ))
    await asyncio.wait_for(empezado.wait(), 10)
    # Lo mismo que hace `DELETE /agents/{id}/run` con la tarea de este worker.
    orquestador.active_tasks[article_id].cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(tarea, 15)
    return article_id


async def _pasos(article_id):
    async with AsyncSessionLocal() as session:
        stmt = select(AgentRunStepModel).where(AgentRunStepModel.article_id == article_id)
        return list((await session.execute(stmt)).scalars().all())


@pytest.mark.asyncio
async def test_cancelar_pide_la_descarga_del_modelo_del_agente(db, runs, redactor_colgado, monkeypatch):
    """AC1/AC2/AC5: el modelo que resolvió el agente cancelado se descarga explícitamente."""
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "ollama", raising=False)
    descargados = []

    async def _unload(model):
        descargados.append(model)
        return True

    monkeypatch.setattr(llm, "unload_model", _unload)

    article_id = await _lanzar_y_cancelar(redactor_colgado)

    assert descargados == [llm.resolve_agent_model("redactor", {})]
    # La cancelación cierra el run y deja la traza del paso (T9.1/AC1).
    assert runs == ["cancelled"]
    pasos = await _pasos(article_id)
    assert [p.status for p in pasos] == ["cancelled"]
    assert pasos[0].model == descargados[0]


@pytest.mark.asyncio
async def test_cancelar_llega_a_ollama_por_http(db, runs, redactor_colgado, monkeypatch):
    """El camino real, sin sustituir `unload_model`: la petición sale desde una tarea
    ya cancelada, que es justo donde un cliente HTTP podría no llegar a salir."""
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "ollama", raising=False)
    peticiones = _cliente_falso(monkeypatch, lambda r: httpx.Response(200, json={"done": True}))

    await _lanzar_y_cancelar(redactor_colgado)

    assert len(peticiones) == 1
    cuerpo = json.loads(peticiones[0].content)
    assert cuerpo == {
        "model": llm.resolve_agent_model("redactor", {}),
        "prompt": "", "stream": False, "keep_alive": 0,
    }


@pytest.mark.asyncio
async def test_con_proveedor_remoto_cancelar_no_llama_a_ollama(db, runs, redactor_colgado, monkeypatch):
    """AC4, por el camino real: `unload_model` sin sustituir, cliente HTTP vigilado."""
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "anthropic", raising=False)
    peticiones = _cliente_falso(monkeypatch, lambda r: httpx.Response(200, json={}))

    await _lanzar_y_cancelar(redactor_colgado)

    assert peticiones == []
    assert runs == ["cancelled"]


@pytest.mark.asyncio
async def test_si_la_descarga_falla_la_cancelacion_se_completa(db, runs, redactor_colgado, monkeypatch, caplog):
    """AC3: liberar memoria es mejor-esfuerzo; detener el pipeline no."""
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "ollama", raising=False)

    async def _revienta(model):
        raise RuntimeError("Ollama no contesta")

    monkeypatch.setattr(llm, "unload_model", _revienta)

    with caplog.at_level(logging.WARNING):
        article_id = await _lanzar_y_cancelar(redactor_colgado)

    assert "Ollama no contesta" in caplog.text
    assert runs == ["cancelled"]
    assert [p.status for p in await _pasos(article_id)] == ["cancelled"]


@pytest.mark.asyncio
async def test_una_descarga_colgada_no_bloquea_la_cancelacion(db, runs, redactor_colgado, monkeypatch, caplog):
    """AC3: un Ollama que no responde no puede dejar la cancelación esperando."""
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "ollama", raising=False)
    monkeypatch.setattr(orquestador, "UNLOAD_WAIT_SECONDS", 0.2)

    async def _colgada(model):
        await asyncio.sleep(3600)

    monkeypatch.setattr(llm, "unload_model", _colgada)

    inicio = time.perf_counter()
    with caplog.at_level(logging.WARNING):
        await _lanzar_y_cancelar(redactor_colgado)
    assert time.perf_counter() - inicio < 5
    assert "no confirmó la descarga" in caplog.text
    assert runs == ["cancelled"]


# ── Adyacente: cancelar durante el backoff de reintentos ────────────────────

@pytest.mark.asyncio
async def test_cancelar_durante_el_backoff_del_stream_es_inmediato(monkeypatch):
    """`task.cancel()` es cooperativo, pero el backoff espera con `asyncio.sleep`,
    que es un punto de cancelación: no hay que esperar a que venza el retraso."""
    monkeypatch.setattr(llm, "_retry_params", lambda: (3, 60.0, 60.0))
    monkeypatch.setattr(llm, "_backoff_delay", lambda *a: 60.0)
    en_backoff = asyncio.Event()

    async def _falla():
        en_backoff.set()
        raise llm.TransientLLMError("All connection attempts failed")
        yield  # pragma: no cover — lo convierte en generador asíncrono

    async def _consumir():
        async for _ in llm._retry_stream(_falla, what="test"):
            pass

    tarea = asyncio.create_task(_consumir())
    await asyncio.wait_for(en_backoff.wait(), 5)
    await asyncio.sleep(0)  # que entre en el sleep del backoff
    inicio = time.perf_counter()
    tarea.cancel()
    with pytest.raises(asyncio.CancelledError):
        await tarea
    assert time.perf_counter() - inicio < 1
