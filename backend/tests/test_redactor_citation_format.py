"""SPEC-035 / T23.9 / AC10 — el Redactor cita con [F#] y no con autor-año inventado.

Observado de punta a punta con `qwen3.5:9b`: 0 citas [F#] en el cuerpo y citas inventadas como
«(HarnessDev, 2024)» (título como autor, año que no es el de la ficha).

Diagnóstico (ver docs/bitacora/tarea-660.md): el contexto del Redactor llevaba los fragmentos del
Investigador como «[Fuente: Título] [Sub-pregunta qN: …] texto» y la lista «Título (autores, año)»,
SIN marcador; el único bloque con [F#] salía de una segunda consulta RAG propia (título + palabras
clave) que, si fallaba o no coincidía, dejaba el prompt sin ningún marcador. El modelo, además,
no tenía ejemplo del formato ni la prohibición del autor-año.
"""
import asyncio

import pytest

from app.modules.agents.adapters import redactor, revisor
from app.platform import citations as c
from app.platform import explainability
from app.platform import llm as llm_mod
from app.platform.capabilities import binding

# Lo que el Investigador entrega hoy (adapters/investigador.py): texto con «[Fuente: …]» y
# fragmentos estructurados por sub-pregunta.
RESEARCH_DATA = (
    "FUENTES CITABLES (únicas que pueden citarse):\n- Code as Agent Harness (Autor, 2026) — DOI 10.1/x"
    "\n\n---\n\n[Fuente: Code as Agent Harness] [Sub-pregunta q1: Introducción] El harness es un objeto explícito."
)
FRAGS = [
    {"doc_id": "d1", "chunk_id": "p1", "chunk_index": 0, "filename": "harness.pdf",
     "text": "El harness es un objeto explícito, inspeccionable y reutilizable.",
     "origin": "[Sub-pregunta q1: Introducción]"},
    {"doc_id": "d1", "chunk_id": "p2", "chunk_index": 4, "filename": "harness.pdf",
     "text": "La evolución automática no supera a las líneas base de escalado.",
     "origin": "[Sub-pregunta q3: Resultados]"},
]

SIN_CITAS = (
    "## Introducción\n\nLa literatura redefine el harness como un objeto explícito (HarnessDev, 2024). "
    "Además es reutilizable (Code as Agent Harness et al., 2024).\n"
)
CON_CITAS = (
    "## Introducción\n\nLa literatura redefine el harness como un objeto explícito [F1]. "
    "La evolución automática no supera las líneas base [F2].\n"
)

PROMPTS: list = []


def _stream(borradores):
    llamadas = []

    async def falso(prompt, **kw):
        PROMPTS.append(prompt)
        llamadas.append(kw)
        llm_mod._anotar_motivo_parada("stop")
        yield borradores[min(len(llamadas) - 1, len(borradores) - 1)]
    return falso, llamadas


def _estado(borradores, *, fragmentos=FRAGS, rag=None, **extra):
    stream, llamadas = _stream(borradores)

    async def buscar(**kw):
        if rag is Exception:
            raise RuntimeError("qdrant caído")
        return rag or []

    st = {
        "title": "T", "keywords": [], "research_data": RESEARCH_DATA,
        "sources": [{"doc_id": "d1"}], "research_fragments": fragmentos,
        "agent_settings": {}, "article_id": None, "_log": lambda *a, **k: None,
        binding.CLAVE_ESTADO: binding.CapabilityBundle({"rag_results": buscar, "llm_stream": stream}),
    }
    st.update(extra)
    return st, llamadas


# ── Diagnóstico: el contexto real del Redactor ──────────────────────────────

def test_el_contexto_del_investigador_sin_fragmentos_estructurados_no_lleva_marcadores():
    """Reproduce la causa: con la salida del Investigador de antes y el RAG propio sin resultados,
    el prompt del Redactor no contiene ningún [F#]."""
    PROMPTS.clear()
    st, _ = _estado([CON_CITAS], fragmentos=None, rag=[])
    out = asyncio.run(redactor.run_redactor(st))
    assert "### Fragmentos citables" not in PROMPTS[0]
    assert out["citation_map"] == {}


def test_los_fragmentos_por_subpregunta_del_investigador_llevan_marcador_aunque_el_rag_propio_falle():
    PROMPTS.clear()
    st, _ = _estado([CON_CITAS], rag=Exception)
    out = asyncio.run(redactor.run_redactor(st))
    assert "[F1]" in PROMPTS[0] and "[F2]" in PROMPTS[0]
    assert "[Sub-pregunta q1: Introducción]" in PROMPTS[0].split("### Fragmentos citables")[1]
    assert set(out["citation_map"]) == {"F1", "F2"}


def test_el_mismo_fragmento_del_investigador_y_del_rag_no_se_duplica():
    PROMPTS.clear()
    st, _ = _estado([CON_CITAS], rag=[dict(FRAGS[0])])
    out = asyncio.run(redactor.run_redactor(st))
    assert set(out["citation_map"]) == {"F1", "F2"}


def test_fragmentos_de_documentos_fuera_de_sources_no_son_citables():
    PROMPTS.clear()
    ajeno = {"doc_id": "otro", "chunk_index": 0, "filename": "x", "text": "no citable"}
    st, _ = _estado([CON_CITAS], fragmentos=FRAGS + [ajeno])
    asyncio.run(redactor.run_redactor(st))
    assert "no citable" not in PROMPTS[0]


# ── Autor-año no es una cita válida ─────────────────────────────────────────

def test_un_borrador_con_autor_anio_y_ningun_marcador_se_marca_sin_citas_validas():
    mapa = c.assign_cite_ids(FRAGS)
    out = c.extract_citations(SIN_CITAS, mapa)
    assert out["valid_citations"] == 0
    assert out["author_year"] == ["(HarnessDev, 2024)", "(Code as Agent Harness et al., 2024)"]
    # Se tratan como citas sin fragmento: la compuerta las deja not_verified.
    assert [x["fragment_id"] for x in out["citations"]] == [None, None]
    assert out["unresolved"] == out["author_year"]
    ins = c.to_citation_inputs(out["citations"])
    assert ins[0].citation_key == "(HarnessDev, 2024)" and ins[0].doc_id is None


def test_un_parentesis_con_un_anio_que_no_es_cita_no_se_confunde():
    out = c.extract_citations("Se midió en 2024 (véase la tabla) y (en 2024) subió [F1].", c.assign_cite_ids(FRAGS))
    assert out["author_year"] == [] and out["valid_citations"] == 1


# ── Reintento ───────────────────────────────────────────────────────────────

def test_sin_marcadores_habiendo_fragmentos_reintenta_una_vez_con_el_formato_recordado():
    PROMPTS.clear()
    st, llamadas = _estado([SIN_CITAS, CON_CITAS])
    with explainability.collecting():
        out = asyncio.run(redactor.run_redactor(st))
    assert len(llamadas) == 2
    assert "RECORDATORIO OBLIGATORIO DEL FORMATO DE CITA" in PROMPTS[1]
    assert "RECORDATORIO" not in PROMPTS[0]
    assert out["draft_text"] == CON_CITAS
    assert out["citation_check"]["retried"] is True and out["citation_check"]["no_citations"] is False
    assert explainability.decision_of(out)["citation_retry"] is True


def test_el_recordatorio_va_en_el_idioma_del_redactor():
    PROMPTS.clear()
    st, _ = _estado([SIN_CITAS, CON_CITAS], agent_settings={"redactor": {"output_language": "en"}})
    asyncio.run(redactor.run_redactor(st))
    assert "MANDATORY CITATION FORMAT REMINDER" in PROMPTS[1]


def test_si_persiste_se_registra_no_citations_y_el_paso_no_falla():
    st, llamadas = _estado([SIN_CITAS])
    out = asyncio.run(redactor.run_redactor(st))
    assert len(llamadas) == 2, "un solo reintento, no más"
    assert out["draft_text"] == SIN_CITAS
    assert out["citation_check"]["no_citations"] is True
    decision = explainability.decision_of(out)
    assert decision["no_citations"] is True
    assert decision["author_year_citations"] == ["(HarnessDev, 2024)", "(Code as Agent Harness et al., 2024)"]
    assert decision["citable_fragments"] == 2


def test_un_borrador_correcto_no_se_reintenta_ni_deja_traza():
    st, llamadas = _estado([CON_CITAS])
    out = asyncio.run(redactor.run_redactor(st))
    assert len(llamadas) == 1
    assert out["citation_check"]["retried"] is False and out["citation_check"]["no_citations"] is False
    assert explainability.decision_of(out) is None


def test_sin_fragmentos_citables_no_se_exige_ni_se_reintenta():
    st, llamadas = _estado([SIN_CITAS], fragmentos=None, sources=[])
    out = asyncio.run(redactor.run_redactor(st))
    assert len(llamadas) == 1 and out["citation_check"]["no_citations"] is False


# ── Aviso al Revisor ────────────────────────────────────────────────────────

def test_el_revisor_recibe_el_aviso_y_lo_deja_en_el_feedback():
    vistos = []

    async def juez(prompt, **kw):
        vistos.append(prompt)
        return '{"approval_score": 90, "coherent": true, "feedback": []}'

    base = {"draft_text": SIN_CITAS, "agent_settings": {}, "_log": lambda *a, **k: None,
            binding.CLAVE_ESTADO: binding.CapabilityBundle({"llm": juez})}
    con = asyncio.run(revisor.run_revisor({**base, "citation_check": {"no_citations": True}}))
    assert "NO valid [F#]" in vistos[0]
    assert any("[F#]" in f for f in con["feedback"])
    sin = asyncio.run(revisor.run_revisor(dict(base)))
    assert "NO valid [F#]" not in vistos[1] and sin["feedback"] == []


# ── Prompt por defecto es/en ────────────────────────────────────────────────

@pytest.mark.parametrize("plantilla,ejemplo,prohibe", [
    (redactor._DEFAULT_TEMPLATE_ES, "[F1]", "NO uses citas autor-año"),
    (redactor._DEFAULT_TEMPLATE_EN, "[F1]", "Do NOT use author-year citations"),
])
def test_el_prompt_por_defecto_muestra_el_formato_y_prohibe_autor_anio(plantilla, ejemplo, prohibe):
    assert ejemplo in plantilla and prohibe in plantilla


def test_el_bloque_de_fragmentos_prohibe_autor_anio_en_los_dos_idiomas():
    mapa = c.assign_cite_ids(FRAGS)
    assert "autor-año" in c.render_fragments(FRAGS, mapa, "es")
    assert "author-year" in c.render_fragments(FRAGS, mapa, "en")
