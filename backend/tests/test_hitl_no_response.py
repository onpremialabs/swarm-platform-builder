"""SPEC-036 AC9 / T24.8 — sin respuesta a la pausa de decisión no es «continuar»."""
import asyncio
import uuid

import pytest
from sqlalchemy import select

from test_project_isolation import _proyecto, _usuario, db  # noqa: F401  (fixtures y ayudas)
from test_review_exhausted import BUCLE, FLUJO, _articulo, pipeline  # noqa: F401
from app.core.database import AsyncSessionLocal
from app.models import ArticleModel, ArticleStatus
from app.modules.agents.adapters import revisor as adapter_revisor
from app.modules.agents.application import use_cases as orquestador
from app.platform.engine.routing import FIN, NO_RESPONSE, make_review_router
from app.platform.explainability import decision_of

# El revisor real, capturado antes de que la fixture `pipeline` lo sustituya por uno simulado.
_REVISOR_REAL = adapter_revisor.run_revisor


def _revisa(request_decision, **extra):
    async def llm(*a, **k):
        return '{"approval_score": 45, "coherent": false, "feedback": ["falta rigor"]}'

    original = adapter_revisor.call_llm
    adapter_revisor.call_llm = llm
    try:
        estado = {"draft_text": "x", "loop_count": 0, "agent_settings": {}, **extra}
        if request_decision is not None:
            estado["_request_decision"] = request_decision
        return asyncio.run(adapter_revisor.run_revisor(estado))
    finally:
        adapter_revisor.call_llm = original


# ── Enrutador ───────────────────────────────────────────────────────────────


def test_no_response_no_salta_la_revision():
    ruta = make_review_router(BUCLE)
    est = {"flow_sequence": FLUJO, "approval_score": 45, "coherent": False, "user_decision": NO_RESPONSE}
    assert ruta({**est, "loop_count": 1}) == "redactor"
    assert ruta({**est, "loop_count": 3}) == FIN


# ── Revisor ─────────────────────────────────────────────────────────────────


def test_vencer_el_tiempo_deja_sin_decision_y_lo_traza():
    async def nadie(payload):
        return {"decision": NO_RESPONSE, "by": None, "at": "2026-11-26T10:00:00+00:00"}

    out = _revisa(nadie)
    assert out["user_decision"] is None
    assert out["hitl"]["origin"] == "no_response" and out["hitl"]["by"] is None
    d = decision_of(out)
    assert d["hitl_outcome"] == NO_RESPONSE and d["hitl"]["at"]


def test_sin_canal_de_decision_no_continua():
    out = _revisa(None)
    assert out["user_decision"] is None and out["hitl"]["origin"] == "no_channel"


def test_el_tope_de_fuentes_no_se_convierte_en_continuar():
    async def no_debe_llamarse(payload):
        raise AssertionError("no se pregunta")

    out = _revisa(no_debe_llamarse, source_retries=3)
    assert out["user_decision"] is None and out["hitl"]["origin"] == "source_retry_limit"


def test_una_decision_explicita_de_una_persona_salta_y_deja_quien_y_cuando():
    async def persona(payload):
        return {"decision": "continue", "by": "u-1", "at": "2026-11-26T10:01:00+00:00"}

    out = _revisa(persona)
    assert out["user_decision"] == "continue"
    assert out["hitl"] == {"origin": "person", "outcome": "continue", "by": "u-1",
                           "at": "2026-11-26T10:01:00+00:00"}
    assert decision_of(out)["hitl"]["by"] == "u-1"


def test_el_canal_antiguo_que_devuelve_cadena_sigue_valiendo():
    async def vieja(payload):
        return "add_source"

    out = _revisa(vieja)
    assert out["user_decision"] == "add_source" and out["hitl"]["origin"] == "person"


# ── request_user_decision / submit_user_decision ────────────────────────────


@pytest.mark.asyncio
async def test_timeout_no_es_continue_y_se_anuncia(monkeypatch):
    eventos = []
    monkeypatch.setattr(orquestador, "publish_event", lambda aid, ev: eventos.append(ev))
    monkeypatch.setattr(orquestador, "_DECISION_TIMEOUT", 0.05)
    res = await orquestador.request_user_decision(uuid.uuid4(), {"reason": "coherence_failed"})
    assert res["decision"] == NO_RESPONSE and res["by"] is None
    resuelto = next(e for e in eventos if e["type"] == "decision_resolved")
    assert resuelto["timed_out"] is True and resuelto["decision"] == NO_RESPONSE


@pytest.mark.asyncio
async def test_la_decision_de_una_persona_lleva_quien_y_cuando(monkeypatch):
    monkeypatch.setattr(orquestador, "publish_event", lambda aid, ev: None)
    art = uuid.uuid4()
    tarea = asyncio.create_task(orquestador.request_user_decision(art, {}))
    await asyncio.sleep(0.05)
    assert await orquestador.submit_user_decision(art, "continue", by="u-7") is True
    res = await tarea
    assert res["decision"] == "continue" and res["by"] == "u-7" and res["at"]


# ── Pipeline completo: ejecución sin oyente ─────────────────────────────────


@pytest.mark.asyncio
async def test_ejecucion_sin_oyente_con_score_bajo_no_llega_al_formateador(db, pipeline, monkeypatch):
    llamados, eventos = pipeline

    async def llm(*a, **k):
        return '{"approval_score": 45, "coherent": false, "feedback": ["falta rigor"]}'

    async def revisor_real(state):
        llamados.append("revisor")
        return await _REVISOR_REAL(state)

    monkeypatch.setattr(adapter_revisor, "call_llm", llm)
    monkeypatch.setattr(adapter_revisor, "run_revisor", revisor_real)
    # El canal de decisión existe pero vence el tiempo de espera sin respuesta.
    monkeypatch.setattr(orquestador, "_DECISION_TIMEOUT", 0.01)

    autora, art = await _articulo()
    await orquestador.Orchestrator.run(
        article_id=art.id, author_id=autora.id, title="T", keywords=[],
        scientific_format="apa", flow_sequence=FLUJO,
    )
    assert "formateador" not in llamados and "publicador" not in llamados
    assert llamados.count("redactor") == 3  # volvió al Redactor mientras quedaron vueltas
    async with AsyncSessionLocal() as s:
        a = (await s.execute(select(ArticleModel).where(ArticleModel.id == art.id))).scalars().first()
    assert a.status == ArticleStatus.REQUIRES_HUMAN_REVIEW
    assert any(e["type"] == "decision_resolved" and e.get("timed_out") for e in eventos)
