"""El Revisor dimensiona ventana y tiempo por el borrador (SPEC-036 / T24.11 / AC12).

Observado de punta a punta con `qwen3.5:9b`: `timeout=45.0, num_ctx=4096` fijos; un borrador de
2270 palabras agotó 45 s cuatro veces (20 min) y no cabe en 4096 tokens (el proveedor lo
recorta sin avisar). Aquí se defiende que:

* ventana y tiempo salen de la cascada y se dimensionan por el borrador, sin pasar de la
  ventana del modelo;
* un borrador de ~2300 palabras se revisa sin recorte con el LLM falso;
* si el prompt no cabe, no se envía: `not_verified` con motivo y traza;
* un tiempo agotado no se reintenta con el mismo límite: sube una vez o falla con motivo.
"""
import asyncio

import pytest

import app.modules.agents.adapters.revisor as revisor
from app.core import config
from app.platform import explainability, review_budget
from app.platform.llm import (
    LLMTimeoutError, TransientLLMError, _retry_async, resolve_agent_timeout, validate_timeout,
)
from app.platform.publication_gate.review import judgment_blockers

OK = '{"approval_score": 91, "coherent": true, "feedback": ["bien"]}'


def _borrador(palabras: int) -> str:
    return " ".join(["metodología"] * palabras) + "."


def _run(texto, llm, model="qwen3.5:9b", settings=None):
    original = revisor.call_llm, revisor.resolve_agent_model
    revisor.call_llm = llm
    revisor.resolve_agent_model = lambda *a, **k: model
    try:
        state = {"draft_text": texto, "loop_count": 0, "agent_settings": settings or {}}
        return asyncio.run(revisor.run_revisor(state))
    finally:
        revisor.call_llm, revisor.resolve_agent_model = original


def _llm_que_registra(respuestas, llamadas):
    """Doble: una respuesta (o excepción) por llamada; guarda lo que recibió."""
    async def llm(prompt, **kwargs):
        llamadas.append({"prompt": prompt, **kwargs})
        r = respuestas[min(len(llamadas) - 1, len(respuestas) - 1)]
        if isinstance(r, Exception):
            raise r
        return r
    return llm


# ── Dimensionado ────────────────────────────────────────────────────────────
def test_borrador_de_2300_palabras_se_revisa_sin_recorte():
    texto = _borrador(2300)
    llamadas = []
    out = _run(texto, _llm_que_registra([OK], llamadas))

    assert out["review_status"] == "ok" and out["approval_score"] == 91
    assert len(llamadas) == 1
    enviado = llamadas[0]
    assert texto in enviado["prompt"]                      # el borrador entero, sin recortar
    necesario = review_budget.estimate_tokens(enviado["prompt"]) + review_budget.MARGEN_SALIDA_TOKENS
    assert enviado["num_ctx"] >= necesario                 # la ventana lo contiene
    assert enviado["num_ctx"] > 4096                       # ya no es el 4096 fijo
    assert enviado["num_ctx"] <= 32_768                    # techo: ventana de qwen3
    assert enviado["timeout"] > 45.0
    assert enviado["retry_on_timeout"] is False
    traza = out["review_budget"]
    assert traza["outcome"] == "ok" and traza["timeout_retries"] == 0
    assert explainability.decision_of(out)["review_budget"] == traza


def test_borrador_corto_conserva_la_ventana_por_defecto():
    llamadas = []
    _run("Un borrador breve.", _llm_que_registra([OK], llamadas))
    assert llamadas[0]["num_ctx"] == 4096


def test_la_cascada_pone_el_minimo_y_los_ajustes_de_la_ejecucion_mandan():
    llamadas = []
    ajustes = {"revisor": {"num_ctx": 12_000, "timeout_seconds": 500}}
    _run("Un borrador breve.", _llm_que_registra([OK], llamadas), settings=ajustes)
    assert llamadas[0]["num_ctx"] == 12_000 and llamadas[0]["timeout"] == 500.0


def test_el_techo_es_la_ventana_del_modelo():
    b = review_budget.size_review_budget("x", model="llama3", configured_ctx=1_000_000)
    assert b.num_ctx == 8_192 and b.fits


def test_timeout_invalido_cae_al_siguiente_escalon():
    assert resolve_agent_timeout("revisor", {"revisor": {"timeout_seconds": "abc"}}) is None
    assert resolve_agent_timeout("revisor", {"revisor": {"timeout_seconds": 90}}) == 90.0
    for malo in (-5, 0, 1, True, "x", float("nan")):
        with pytest.raises(ValueError):
            validate_timeout("timeout_seconds", malo)


# ── Lo que no cabe ──────────────────────────────────────────────────────────
def test_prompt_que_no_cabe_no_se_envia_y_es_not_verified():
    llamadas = []
    # llama3 → ventana de 8192 tokens; ~9000 palabras no caben ni con toda la ventana.
    out = _run(_borrador(9000), _llm_que_registra([OK], llamadas), model="llama3")
    assert llamadas == []                                   # ni se llamó al proveedor
    assert out["review_status"] == "not_verified"
    assert out["approval_score"] == 0 and out["coherent"] is False and out["feedback"] == []
    assert judgment_blockers(out) == ["review_not_verified"]
    traza = out["review_budget"]
    assert traza["outcome"] == "prompt_exceeds_window" and traza["fits"] is False
    assert traza["model_window"] == 8_192 and traza["prompt_tokens"] > 8_192
    assert explainability.decision_of(out)["review_budget"]["outcome"] == "prompt_exceeds_window"


# ── Tiempo agotado ──────────────────────────────────────────────────────────
def test_timeout_sube_el_presupuesto_una_vez_y_no_repite_el_limite():
    llamadas = []
    out = _run("Un borrador.", _llm_que_registra([LLMTimeoutError("t", timeout=120), OK], llamadas))
    primero, segundo = (c["timeout"] for c in llamadas)
    assert segundo == primero * 2 and segundo != primero    # sube; no repite el mismo límite
    assert out["review_status"] == "ok"
    assert out["review_budget"]["timeout_retries"] == 1
    assert out["review_budget"]["timeout"] == round(segundo, 1)


def test_timeout_dos_veces_falla_con_motivo_y_traza():
    llamadas = []
    out = _run("Un borrador.", _llm_que_registra([LLMTimeoutError("t")], llamadas))
    assert len(llamadas) == 2                               # no 4 intentos con el mismo límite
    assert out["review_status"] == "not_verified" and out["approval_score"] == 0
    traza = out["review_budget"]
    assert traza["outcome"] == "timeout" and traza["timeout_retries"] == 1
    assert "elapsed_seconds" in traza


# ── Capa de reintentos ──────────────────────────────────────────────────────
def test_retry_async_propaga_el_timeout_si_se_pide(monkeypatch):
    monkeypatch.setattr(config.settings, "LLM_RETRY_BASE_DELAY", 0.0, raising=False)
    intentos = []

    async def f():
        intentos.append(1)
        raise LLMTimeoutError("t")

    with pytest.raises(LLMTimeoutError):
        asyncio.run(_retry_async(f, what="x", retry_on_timeout=False))
    assert len(intentos) == 1

    intentos.clear()
    with pytest.raises(LLMTimeoutError):
        asyncio.run(_retry_async(f, what="x"))             # comportamiento de siempre
    assert len(intentos) > 1


def test_otros_fallos_transitorios_se_siguen_reintentando(monkeypatch):
    monkeypatch.setattr(config.settings, "LLM_RETRY_BASE_DELAY", 0.0, raising=False)
    intentos = []

    async def f():
        intentos.append(1)
        if len(intentos) < 2:
            raise TransientLLMError("conexión")
        return "ok"

    assert asyncio.run(_retry_async(f, what="x", retry_on_timeout=False)) == "ok"


# ── Paridad adapters / capabilities y validación al cargar ──────────────────
def test_paridad_adapters_capabilities_mismo_presupuesto():
    """Con `llm` inyectada por el bundle el Revisor dimensiona y reintenta igual."""
    from app.platform.capabilities.binding import CLAVE_ESTADO, CapabilityBundle

    resultados = []
    for via_bundle in (False, True):
        llamadas = []
        llm = _llm_que_registra([LLMTimeoutError("t"), OK], llamadas)
        extra = {CLAVE_ESTADO: CapabilityBundle(proveedores={"llm": llm})} if via_bundle else {}
        original = revisor.call_llm
        revisor.call_llm = llm  # el camino heredado usa el import de siempre
        try:
            out = asyncio.run(revisor.run_revisor(
                {"draft_text": _borrador(2300), "loop_count": 0, "agent_settings": {}, **extra}))
        finally:
            revisor.call_llm = original
        resultados.append((
            [(c["num_ctx"], c["timeout"], c["retry_on_timeout"]) for c in llamadas],
            out["review_status"], out["review_budget"]["timeout_retries"],
        ))
    assert resultados[0] == resultados[1]


def test_el_revisor_no_tiene_limites_fijos_en_el_codigo():
    from pathlib import Path
    fuente = Path(revisor.__file__).read_text(encoding="utf-8")
    assert "timeout=45" not in fuente and "num_ctx=4096" not in fuente


def test_un_perfil_con_timeout_invalido_no_carga(tmp_path):
    from app.platform.projects import loader

    perfil = tmp_path / "x.agent.md"
    perfil.write_text("---\nname: x\ntimeout_seconds: -3\n---\n# x\n", encoding="utf-8")
    with pytest.raises(loader.TemplateError, match="timeout_seconds"):
        loader._validar_limites_perfil("x", perfil)
    perfil.write_text("---\nname: x\ntimeout_seconds: 300\nnum_ctx: 8192\n---\n# x\n", encoding="utf-8")
    loader._validar_limites_perfil("x", perfil)
