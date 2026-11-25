"""El Redactor no entrega un borrador cortado (SPEC-036 / T24.9 / AC10).

Observado de punta a punta con `qwen3.5:9b`: el borrador acabó en «…métricas como el tiempo
de», sin Discusión, porque `num_ctx=4096` estaba fijo en el código y la salida se cortó a
≈2046 tokens. El proveedor respondió 200 y el texto siguió al Revisor y al Publicador.

Lo que se defiende aquí:

* un texto cortado a mitad de frase **no pasa al Revisor**: se reintenta con más presupuesto
  y, si persiste, el paso falla con motivo;
* lo no truncado sigue igual (una sola generación, sin traza de truncado);
* el límite se resuelve por la cascada de modelo/temperatura y se acota a la ventana.
"""
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

import app.platform.llm as llm  # noqa: E402
from app.core import config  # noqa: E402
from app.modules.agents.adapters import redactor  # noqa: E402
from app.platform import draft_integrity, explainability  # noqa: E402

COMPLETO = (
    "# Titulo\n\n## Resumen\n\nResumen del trabajo.\n\n## Introducción\n\nContexto.\n\n"
    "## Metodología\n\nMétodo.\n\n## Resultados\n\nHallazgos.\n\n## Discusión\n\nCierre del texto."
)
#: Lo que se vio de verdad: sin Discusión y cortado a mitad de frase.
CORTADO = (
    "# Titulo\n\n## Resumen\n\nResumen.\n\n## Introducción\n\nContexto.\n\n"
    "## Metodología\n\nMétodo.\n\n## Resultados\n\nSe midieron métricas como el tiempo de"
)


@pytest.fixture
def ollama(monkeypatch):
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "ollama", raising=False)


def _estado(**extra):
    base = {"title": "T", "keywords": [], "research_data": "datos", "feedback": [],
            "agent_settings": {}, "_log": lambda *a, **k: None, "_emit_token": lambda t: None}
    base.update(extra)
    return base


def _stream(respuestas, llamadas):
    """Doble de `call_llm_stream`: una respuesta por llamada, con su motivo de parada."""
    async def falso(prompt, **kwargs):
        llamadas.append(kwargs)
        texto, motivo = respuestas[min(len(llamadas) - 1, len(respuestas) - 1)]
        llm._anotar_motivo_parada(motivo)
        yield texto
    return falso


# ── Detección ───────────────────────────────────────────────────────────────

def test_el_motivo_de_parada_del_proveedor_manda_sobre_el_texto():
    assert draft_integrity.detect_truncation(COMPLETO, "length")["signal"] == "stop_reason"
    assert draft_integrity.detect_truncation(COMPLETO, "max_tokens")["signal"] == "stop_reason"


def _secciones():
    from app.modules.agents.domain import alejandria
    return draft_integrity.required_sections(alejandria.package().gate)


def test_un_stop_normal_ya_no_exculpa_al_texto_cortado():
    """AC11: la heurística se aplica siempre; la parada normal no la apaga."""
    d = draft_integrity.detect_truncation(CORTADO, "stop", sections=_secciones())
    assert d["signal"] == "heuristic" and d["signals"] == ["heuristic"] and d["stop_reason"] == "stop"
    assert "discussion" in d["missing_sections"]


def test_el_caso_harnessdev_con_parada_normal_es_truncado():
    texto = COMPLETO.split("## Discusión")[0] + "Como en (HarnessDev, 2024"
    d = draft_integrity.detect_truncation(texto, "stop", sections=_secciones())
    assert d is not None and "unterminated_sentence" in d["reasons"]
    assert d["missing_sections"] == ["discussion"]


def test_el_corte_del_proveedor_suma_su_senal_a_la_heuristica():
    d = draft_integrity.detect_truncation(CORTADO, "length", sections=_secciones())
    assert d["signal"] == "stop_reason" and d["signals"] == ["stop_reason", "heuristic"]


def test_sin_motivo_la_heuristica_ve_el_corte_a_mitad_de_frase():
    diagnostico = draft_integrity.detect_truncation(CORTADO, None, sections=_secciones())
    assert diagnostico["signal"] == "heuristic"
    assert "unterminated_sentence" in diagnostico["reasons"]
    assert "discussion" in diagnostico["missing_sections"]


def test_un_borrador_entero_no_se_marca():
    for motivo in (None, "stop"):
        assert draft_integrity.detect_truncation(COMPLETO, motivo, sections=_secciones()) is None


def test_no_se_exige_references_al_redactor():
    assert "references" not in [c for c, _ in _secciones()]


def test_sin_falsos_positivos_por_idioma_ni_por_variante_de_titulo():
    ingles = ("# T\n\n## Abstract\n\nA.\n\n## 1. Introduction\n\nB.\n\n## Materials and Methods\n\nC.\n\n"
              "## Results\n\nD.\n\n## Discussion\n\nFin.")
    mezcla = COMPLETO.replace("## Metodología", "## Métodos").replace("## Resultados", "**Resultados**")
    fundido = COMPLETO.replace("## Resultados\n\nHallazgos.\n\n## Discusión", "## Resultados y Discusión")
    for texto in (ingles, mezcla, fundido):
        assert draft_integrity.detect_truncation(texto, "stop", sections=_secciones()) is None, texto


def test_las_secciones_salen_de_la_plantilla_no_del_codigo():
    class Gate:
        sections = ("alpha", "references")
        titles = {"xx": {"alpha": ("Zeta",)}}

    assert draft_integrity.required_sections(Gate()) == [("alpha", ("zeta",))]
    assert draft_integrity.required_sections(None) == []


# ── El caso del DoD ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_un_borrador_cortado_a_mitad_de_frase_no_pasa_al_revisor(ollama, monkeypatch):
    """Cortado en el primer intento y en el reintento: el paso FALLA, no devuelve `draft_text`."""
    llamadas = []
    monkeypatch.setattr(redactor, "call_llm_stream", _stream([(CORTADO, "length")], llamadas))

    with pytest.raises(RuntimeError, match="truncado"):
        await redactor.run_redactor(_estado())

    assert len(llamadas) == 2, "debe reintentar una vez, no más"


@pytest.mark.asyncio
async def test_el_reintento_recibe_mas_presupuesto_y_el_borrador_entero_se_entrega(ollama, monkeypatch):
    llamadas = []
    monkeypatch.setattr(
        redactor, "call_llm_stream", _stream([(CORTADO, "length"), (COMPLETO, "stop")], llamadas),
    )
    with explainability.collecting() as traza:
        salida = await redactor.run_redactor(_estado())

    assert salida["draft_text"] == COMPLETO
    assert llamadas[0]["num_ctx"] == 4096
    assert llamadas[1]["num_ctx"] == 8192
    # El truncado queda en la traza, aunque el reintento lo enmendara.
    assert len(traza.truncations) == 1 and traza.truncations[0]["signal"] == "stop_reason"
    decision = explainability.with_truncations(None, traza.truncations)
    assert decision["truncation"][0]["num_ctx"] == 4096


@pytest.mark.asyncio
async def test_sin_motivo_de_parada_la_heuristica_tambien_reintenta(ollama, monkeypatch):
    llamadas = []
    monkeypatch.setattr(
        redactor, "call_llm_stream", _stream([(CORTADO, None), (COMPLETO, None)], llamadas),
    )
    salida = await redactor.run_redactor(_estado())
    assert salida["draft_text"] == COMPLETO and len(llamadas) == 2


@pytest.mark.asyncio
async def test_lo_no_truncado_sigue_igual(ollama, monkeypatch):
    llamadas = []
    monkeypatch.setattr(redactor, "call_llm_stream", _stream([(COMPLETO, "stop")], llamadas))
    with explainability.collecting() as traza:
        salida = await redactor.run_redactor(_estado())

    assert salida["draft_text"] == COMPLETO
    assert len(llamadas) == 1
    assert llamadas[0]["num_ctx"] == 4096 and llamadas[0]["max_tokens"] is None
    assert traza.truncations == []
    assert explainability.with_truncations({"score": 90}, traza.truncations) == {"score": 90}


@pytest.mark.asyncio
async def test_si_no_hay_mas_presupuesto_que_dar_falla_sin_reintentar(ollama, monkeypatch):
    llamadas = []
    monkeypatch.setattr(redactor, "call_llm_stream", _stream([(CORTADO, "length")], llamadas))
    # Un modelo de ventana 32k con num_ctx ya en 32k: reintentar sería repetir lo mismo.
    ajustes = {"redactor": {"model": "qwen3.5:9b", "num_ctx": 32768}}
    with pytest.raises(RuntimeError, match="no hay más presupuesto"):
        await redactor.run_redactor(_estado(agent_settings=ajustes))
    assert len(llamadas) == 1


# ── La cascada del límite ───────────────────────────────────────────────────

def test_el_defecto_es_el_4096_de_siempre(ollama):
    assert llm.resolve_agent_num_ctx("agente-sin-perfil", {}) == 4096
    assert llm.resolve_agent_max_output_tokens("agente-sin-perfil", {}) is None


def test_los_ajustes_de_la_ejecucion_mandan_sobre_el_perfil(ollama):
    ajustes = {"redactor": {"num_ctx": 6000, "max_output_tokens": 3000}}
    assert llm.resolve_agent_num_ctx("redactor", ajustes) == 6000
    assert llm.resolve_agent_max_output_tokens("redactor", ajustes) == 3000


def test_el_perfil_agent_md_es_el_segundo_escalon(ollama):
    assert llm.resolve_agent_num_ctx("redactor", {}) == 4096  # `num_ctx: 4096` del perfil


def test_un_valor_invalido_se_ignora_y_cae_al_siguiente_escalon(ollama):
    assert llm.resolve_agent_num_ctx("redactor", {"redactor": {"num_ctx": "mucho"}}) == 4096
    assert llm.resolve_agent_num_ctx("redactor", {"redactor": {"num_ctx": 10}}) == 4096
    assert llm.resolve_agent_max_output_tokens("redactor", {"redactor": {"max_output_tokens": -1}}) is None


def test_el_limite_se_acota_por_la_ventana_del_modelo(ollama):
    ajustes = {"redactor": {"num_ctx": 1_000_000, "max_output_tokens": 1_000_000}}
    ventana = llm.model_context_window("qwen3.5:9b")
    assert ventana == 32_768
    assert llm.resolve_agent_num_ctx("redactor", ajustes, "qwen3.5:9b") == ventana
    assert llm.resolve_agent_max_output_tokens("redactor", ajustes, "qwen3.5:9b") == ventana


def test_el_reintento_nunca_pasa_de_la_ventana():
    assert llm.enlarge_output_budget(4096, None, "qwen3.5:9b", "ollama") == (8192, None)
    assert llm.enlarge_output_budget(30000, None, "qwen3.5:9b", "ollama") == (32768, None)
    assert llm.enlarge_output_budget(32768, None, "qwen3.5:9b", "ollama") == (32768, None)
    assert llm.enlarge_output_budget(4096, 4000, "claude-sonnet-5", "anthropic") == (4096, 8000)


def test_el_redactor_la_resuelve_por_la_cascada_y_no_la_deja_fija():
    fuente = (ROOT_DIR / "app" / "modules" / "agents" / "adapters" / "redactor.py").read_text(encoding="utf-8")
    assert "resolve_agent_num_ctx" in fuente and "resolve_agent_max_output_tokens" in fuente
    assert "num_ctx=4096" not in fuente


@pytest.mark.parametrize("agente", ["investigador", "revisor", "formateador"])
def test_los_demas_agentes_no_cambian_de_comportamiento(agente):
    """No resuelven ni pasan el tope de salida: siguen con el defecto del proveedor."""
    fuente = (ROOT_DIR / "app" / "modules" / "agents" / "adapters" / f"{agente}.py").read_text(encoding="utf-8")
    assert "max_output_tokens" not in fuente and "resolve_agent_num_ctx" not in fuente


# ── Validación al cargar el perfil ──────────────────────────────────────────

def test_un_perfil_con_limite_invalido_no_carga(tmp_path):
    from app.platform.projects import loader

    perfil = tmp_path / "x.agent.md"
    perfil.write_text("---\nname: x\nnum_ctx: abc\n---\n# x\n", encoding="utf-8")
    with pytest.raises(loader.TemplateError, match="num_ctx"):
        loader._validar_limites_perfil("x", perfil)


def test_el_perfil_del_redactor_carga_con_su_limite():
    from app.platform.projects import loader

    perfil = ROOT_DIR / "projects" / "alejandria-magazine" / "agents" / "redactor.agent.md"
    loader._validar_limites_perfil("redactor", perfil)


# ── El dispatcher expone el motivo de parada sin romper a nadie ──────────────

@pytest.mark.asyncio
async def test_ollama_expone_done_reason_y_num_predict(ollama, monkeypatch):
    recibido = {}

    async def _falso(**kwargs):
        recibido.update(kwargs)
        llm._anotar_motivo_parada("length")
        yield "t"

    monkeypatch.setattr(llm, "_call_ollama_stream", _falso)
    assert [t async for t in llm.call_llm_stream("p", model="m", max_tokens=900)] == ["t"]
    assert recibido["num_predict"] == 900
    assert llm.last_stop_reason() == "length"


@pytest.mark.asyncio
async def test_sin_max_tokens_los_proveedores_no_reciben_el_argumento(monkeypatch):
    """Quien llama a `call_llm_stream` como antes no ve ningún cambio."""
    for nombre, funcion in (("anthropic", "_call_anthropic_stream"), ("openai", "_call_openai_stream"),
                            ("ollama", "_call_ollama_stream")):
        monkeypatch.setattr(config.settings, "LLM_PROVIDER", nombre, raising=False)
        recibido = {}

        async def _falso(**kwargs):
            recibido.update(kwargs)
            yield "t"

        monkeypatch.setattr(llm, funcion, _falso)
        [t async for t in llm.call_llm_stream("p", model="m")]
        assert "max_tokens" not in recibido and "num_predict" not in recibido


# ── AC11 de punta a punta ───────────────────────────────────────────────────

HARNESSDEV = COMPLETO.split("## Discusión")[0] + "Como señalan (HarnessDev, 2024"


@pytest.mark.asyncio
async def test_harnessdev_con_parada_normal_no_pasa_al_revisor(ollama, monkeypatch):
    llamadas = []
    monkeypatch.setattr(redactor, "call_llm_stream", _stream([(HARNESSDEV, "stop")], llamadas))
    with explainability.collecting() as traza:
        with pytest.raises(RuntimeError, match="truncado"):
            await redactor.run_redactor(_estado())
    assert len(llamadas) == 2, "un reintento aunque no haya más presupuesto que dar"
    assert traza.truncations[0]["signal"] == "heuristic"


@pytest.mark.asyncio
async def test_harnessdev_con_parada_normal_se_recupera_si_el_reintento_sale_entero(ollama, monkeypatch):
    llamadas = []
    monkeypatch.setattr(redactor, "call_llm_stream", _stream([(HARNESSDEV, "stop"), (COMPLETO, "stop")], llamadas))
    salida = await redactor.run_redactor(_estado())
    assert salida["draft_text"] == COMPLETO and len(llamadas) == 2


@pytest.mark.asyncio
async def test_borrador_completo_con_parada_normal_no_se_reintenta(ollama, monkeypatch):
    llamadas = []
    monkeypatch.setattr(redactor, "call_llm_stream", _stream([(COMPLETO, "stop")], llamadas))
    await redactor.run_redactor(_estado())
    assert len(llamadas) == 1


@pytest.mark.asyncio
async def test_esquema_del_autor_no_exige_secciones_que_no_pidio(ollama, monkeypatch):
    """Con `article_outline` las secciones son las del autor: no falla por faltar «Discusión»."""
    libre = "# T\n\n## Contexto\n\nTexto.\n\n## Hallazgos\n\nFin del texto."
    llamadas = []
    monkeypatch.setattr(redactor, "call_llm_stream", _stream([(libre, "stop")], llamadas))
    salida = await redactor.run_redactor(_estado(article_outline="Contexto; Hallazgos"))
    assert salida["draft_text"] == libre and len(llamadas) == 1
