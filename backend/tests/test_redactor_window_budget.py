"""El Redactor dimensiona su ventana por el prompt (SPEC-036 / T24.12 / AC13).

Reproducido de punta a punta con `qwen3.5:9b` y `num_ctx=16384`: el prompt con 31 fragmentos
citables llenaba la ventana, el proveedor cortaba con `length` a los ~107 s y el reintento de
AC10 (32768) tardaba 231 s mas. Cada ejecucion perdia un intento entero. Aqui se defiende que:

* la ventana sale del prompt + el margen de salida, con `num_ctx` de la cascada como MINIMO;
* un prompt de ~16 000 tokens con `num_ctx=16384` se envia de una vez con ventana mayor, sin
  corte ni reintento;
* si no cabe en la ventana del modelo, se quitan fragmentos por prioridad de seccion y queda
  en la traza cuantos y por que; si ni asi cabe, el paso falla antes de generar;
* el reintento de AC10 sigue existiendo para cortes imprevistos.
"""
import pytest

import app.platform.llm as llm
from app.core import config
from app.modules.agents.adapters import redactor
from app.platform import explainability, prompt_trim, review_budget

COMPLETO = (
    "# Titulo\n\n## Resumen\n\nResumen del trabajo.\n\n## Introducción\n\nContexto.\n\n"
    "## Metodología\n\nMétodo.\n\n## Resultados\n\nHallazgos [F1].\n\n## Discusión\n\nCierre del texto."
)
MODELO = "qwen3.5:9b"  # ventana de 32768 en la tabla del dispatcher
#: Borrador del tamano pedido (2000 palabras): sin ampliacion de palabras de por medio.
LARGO = COMPLETO + " " + ("palabra " * 2000).strip() + "."
SUBPREGUNTAS = [
    {"id": "q1", "section": "problem"}, {"id": "q2", "section": "method"},
    {"id": "q3", "section": "results"}, {"id": "q4", "section": "limitations"},
]


@pytest.fixture
def ollama(monkeypatch):
    monkeypatch.setattr(config.settings, "LLM_PROVIDER", "ollama", raising=False)


def _fragmentos(n_por_seccion, caracteres, sin_seccion=0):
    """Fragmentos con origen de sub-pregunta; `caracteres` por fragmento."""
    salida = []
    for q in SUBPREGUNTAS:
        for k in range(n_por_seccion):
            salida.append({
                "doc_id": f"d-{q['id']}", "chunk_index": k, "filename": f"{q['id']}.pdf",
                "text": ("palabra " * (caracteres // 8)).strip(), "origin": f"[Sub-pregunta {q['id']}: x]",
            })
    for k in range(sin_seccion):
        salida.append({"doc_id": "d-q1", "chunk_index": 100 + k, "filename": "rag.pdf",
                       "text": ("palabra " * (caracteres // 8)).strip()})
    return salida


def _estado(fragmentos, **extra):
    base = {
        "title": "T", "keywords": [], "research_data": "datos", "feedback": [],
        "agent_settings": {"redactor": {"model": MODELO}},
        "sources": [{"doc_id": f"d-{q['id']}"} for q in SUBPREGUNTAS],
        "research_fragments": fragmentos,
        "research_coverage": {"subqueries": SUBPREGUNTAS},
        "_log": lambda *a, **k: None, "_emit_token": lambda t: None,
    }
    base.update(extra)
    return base


def _stream(respuestas, llamadas):
    async def falso(prompt, **kwargs):
        llamadas.append({"prompt": prompt, **kwargs})
        texto, motivo = respuestas[min(len(llamadas) - 1, len(respuestas) - 1)]
        llm._anotar_motivo_parada(motivo)
        yield texto
    return falso


@pytest.fixture(autouse=True)
def sin_rag(monkeypatch):
    async def vacio(**kwargs):
        return []
    monkeypatch.setattr(redactor, "semantic_search_results", vacio)


# -- Funcion pura -------------------------------------------------------------

def test_la_ventana_configurada_es_minimo_no_tope():
    chico = review_budget.size_window("x" * 300, model="qwen3.5:9b", configured_ctx=16384, output_margin=1024)
    assert chico.num_ctx == 16384 and chico.fits
    grande = review_budget.size_window("x" * 48_000, model="qwen3.5:9b", configured_ctx=16384, output_margin=2048)
    assert grande.prompt_tokens == 16_000 and grande.num_ctx == 18432 and grande.fits
    sin_cupo = review_budget.size_window("x" * 120_000, model="qwen3.5:9b", configured_ctx=16384, output_margin=2048)
    assert not sin_cupo.fits and sin_cupo.num_ctx == sin_cupo.model_window


def test_el_margen_de_salida_sale_del_tope_o_de_las_palabras():
    assert review_budget.writer_output_margin(3000, 2000) == 3000
    assert review_budget.writer_output_margin(None, 2000) == 4000
    assert review_budget.writer_output_margin(None, 100) == review_budget.MARGEN_REDACTOR_MINIMO
    assert review_budget.writer_output_margin(None, 0) == review_budget.MARGEN_REDACTOR_SIN_OBJETIVO


def test_el_orden_de_recorte_protege_la_cobertura_de_las_secciones():
    frags = _fragmentos(2, 80, sin_seccion=1)
    orden = list(prompt_trim.trim_order(frags, SUBPREGUNTAS))
    assert orden[0][2] == "no_section"
    sobrantes = [o for o in orden if o[2] == "section_surplus"]
    assert len(sobrantes) == 4 and sobrantes[0][1] == "limitations"
    perdida = [o[1] for o in orden if o[2] == "section_coverage_lost"]
    assert perdida == ["limitations", "results", "method", "problem"]


# -- El caso del DoD ----------------------------------------------------------

@pytest.mark.asyncio
async def test_prompt_de_16000_tokens_se_envia_con_ventana_mayor_sin_reintento(ollama, monkeypatch):
    """31 fragmentos y ~16 000 tokens con num_ctx=16384: una sola generacion, ventana mayor."""
    llamadas = []
    monkeypatch.setattr(redactor, "call_llm_stream", _stream([(LARGO, "stop")], llamadas))
    frags = _fragmentos(7, 1_580, sin_seccion=3)  # 31 fragmentos
    estado = _estado(frags, agent_settings={"redactor": {"model": MODELO, "num_ctx": 16384, "target_word_count": 2000}})
    with explainability.collecting() as traza:
        salida = await redactor.run_redactor(estado)

    assert salida["draft_text"] == LARGO
    assert len(llamadas) == 1, "no hubo corte ni reintento"
    tokens = review_budget.estimate_tokens(llamadas[0]["prompt"])
    assert 15_500 <= tokens <= 17_500, tokens
    assert llamadas[0]["num_ctx"] > 16384
    assert llamadas[0]["num_ctx"] % review_budget.REDONDEO_VENTANA == 0
    assert llamadas[0]["num_ctx"] <= llm.model_context_window("qwen3.5:9b")
    assert traza.truncations == []
    pb = traza.prompt_budget
    assert pb["outcome"] == "ok" and pb["fragments_removed"] == 0 and pb["configured_num_ctx"] == 16384
    assert explainability.with_prompt_budget(None, pb)["prompt_budget"]["num_ctx"] == llamadas[0]["num_ctx"]


@pytest.mark.asyncio
async def test_prompt_que_no_cabe_quita_fragmentos_por_prioridad_y_lo_registra(ollama, monkeypatch):
    llamadas = []
    monkeypatch.setattr(redactor, "call_llm_stream", _stream([(COMPLETO, "stop")], llamadas))
    # ~40 000 tokens de fragmentos: no caben en 32768 (ventana de qwen3).
    frags = _fragmentos(8, 4_000, sin_seccion=4)
    estado = _estado(frags, agent_settings={"redactor": {"model": MODELO, "num_ctx": 16384}})
    with explainability.collecting() as traza:
        salida = await redactor.run_redactor(estado)

    assert salida["draft_text"] == COMPLETO and len(llamadas) == 1
    assert llamadas[0]["num_ctx"] <= llm.model_context_window("qwen3.5:9b")
    pb = traza.prompt_budget
    assert pb["outcome"] == "trimmed" and pb["reason"] == "prompt_exceeds_model_window"
    assert pb["fragments_total"] == 36 and pb["fragments_removed"] == len(pb["removed"]) > 0
    # Primero los que no se sabe a que seccion sirven; ninguna seccion se quedo sin cobertura.
    assert [r["reason"] for r in pb["removed"][:4]] == ["no_section"] * 4
    assert pb["sections_lost"] == []
    # La numeracion [F#] sale de los fragmentos que se quedan.
    assert len(salida["citation_map"]) == 36 - pb["fragments_removed"]


@pytest.mark.asyncio
async def test_si_ni_recortando_cabe_falla_antes_de_generar(ollama, monkeypatch):
    llamadas = []
    monkeypatch.setattr(redactor, "call_llm_stream", _stream([(COMPLETO, "stop")], llamadas))
    # El contexto solo ya excede la ventana: los fragmentos no lo arreglan.
    estado = _estado(_fragmentos(2, 800), research_data="contexto " * 20_000)
    with explainability.collecting() as traza:
        with pytest.raises(RuntimeError, match="no cabe en la ventana"):
            await redactor.run_redactor(estado)

    assert llamadas == [], "no se genero nada con una ventana que ya se sabia insuficiente"
    pb = traza.prompt_budget
    assert pb["outcome"] == "does_not_fit" and pb["fragments_removed"] == 7  # deja 1


@pytest.mark.asyncio
async def test_el_reintento_de_ac10_sigue_para_cortes_imprevistos(ollama, monkeypatch):
    llamadas = []
    cortado = "# T\n\n## Resumen\n\nA.\n\n## Introducción\n\nB.\n\n## Metodología\n\nC de"
    monkeypatch.setattr(redactor, "call_llm_stream", _stream([(cortado, "length"), (COMPLETO, "stop")], llamadas))
    with explainability.collecting() as traza:
        salida = await redactor.run_redactor(_estado(_fragmentos(1, 400)))
    assert salida["draft_text"] == COMPLETO and len(llamadas) == 2
    assert llamadas[1]["num_ctx"] == min(llamadas[0]["num_ctx"] * 2, llm.model_context_window("qwen3.5:9b"))
    assert len(traza.truncations) == 1
