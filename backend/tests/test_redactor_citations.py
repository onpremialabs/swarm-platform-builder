"""SPEC-035 / T23.1 — el Redactor cita por identificador de fragmento (contrato en platform/citations.py)."""
import asyncio

from app.modules.agents.adapters import redactor
from app.platform import citations as c

R1 = {"doc_id": "d1", "chunk_index": 0, "filename": "a.pdf", "text": "La metformina reduce la HbA1c un 1,1 %."}
R2 = {"doc_id": "d1", "chunk_index": 3, "filename": "a.pdf", "text": "No hubo diferencias en peso."}
R3 = {"doc_id": "d2", "chunk_index": None, "chunk_id": "pt-9", "filename": "b.pdf", "text": "Otro hallazgo."}


def test_el_identificador_es_estable_y_sin_orden():
    assert c.fragment_id(R1) == "d1#0"
    assert c.fragment_id(R3) == "d2#pt-9"
    assert c.fragment_id({"text": "x"}) is None
    a = c.assign_cite_ids([R1, R2])
    b = c.assign_cite_ids([R2, R1])
    assert a["F1"]["fragment_id"] == "d1#0" and b["F1"]["fragment_id"] == "d1#3"


def test_la_entrada_lleva_extracto_hash_y_pagina_nula():
    e = c.assign_cite_ids([R1])["F1"]
    assert set(e) == {"fragment_id", "doc_id", "chunk_index", "filename", "page", "extract", "hash"}
    assert e["hash"] == c.text_hash(R1["text"]) and e["page"] is None


def test_los_alias_se_conservan_entre_vueltas():
    previo = c.assign_cite_ids([R1, R2])
    nuevo = c.assign_cite_ids([R3, R2], previous=previo)
    assert nuevo["F2"]["fragment_id"] == "d1#3"
    assert nuevo["F3"]["fragment_id"] == "d2#pt-9"


def test_extrae_citas_y_marca_las_inventadas():
    mapa = c.assign_cite_ids([R1, R2])
    texto = "## Resultados\n\nLa HbA1c bajó [F1]. El peso no cambió [F2, F9]. Sin cita."
    out = c.extract_citations(texto, mapa)
    ids = [x["cite_id"] for x in out["citations"]]
    assert ids == ["F1", "F2", "F9"]
    assert out["unresolved"] == ["F9"]
    assert out["citations"][0]["claim"] == "La HbA1c bajó."
    assert out["citations"][0]["fragment_id"] == "d1#0"
    assert out["citations"][2]["fragment_id"] is None
    assert set(out["map"]) == {"F1", "F2"}
    assert out["text_hash"] == c.text_hash(texto)


def _state(sources, buscar, **extra):
    from app.platform.capabilities import binding
    st = {
        "title": "T", "keywords": [], "sources": sources, "research_data": "ctx",
        "agent_settings": {}, "article_id": None,
        binding.CLAVE_ESTADO: binding.CapabilityBundle({
            "rag_results": buscar,
            "llm_stream": _llm,
        }),
    }
    st.update(extra)
    return st


PROMPTS = []


async def _llm(prompt, **kw):
    PROMPTS.append(prompt)
    __import__("app.platform.llm", fromlist=["x"])._anotar_motivo_parada("stop")  # el proveedor declara fin natural
    # Borrador entero (T24.10): con parada normal la heuristica igual exige las secciones.
    yield "## Introducción\n\nTexto.\n\n## Metodología\n\nTexto.\n\n## Resultados\n\nTexto.\n\n## Discusión\n\n" + "Texto citado [F1] y falso [F7]."


def test_el_redactor_solo_ofrece_fragmentos_de_sources_y_devuelve_el_mapa():
    PROMPTS.clear()
    visto = {}

    async def buscar(**kw):
        visto.update(kw)
        return [R1, {"doc_id": "ajeno", "chunk_index": 1, "filename": "x", "text": "no citable"}]

    out = asyncio.run(redactor.run_redactor(_state([{"doc_id": "d1"}], buscar)))
    assert visto["doc_ids"] == ["d1"]
    assert "[F1]" in PROMPTS[0] and "no citable" not in PROMPTS[0]
    assert list(out["citation_map"]) == ["F1"]
    assert out["citations_unresolved"] == ["F7"]
    assert out["citations"][0]["fragment_id"] == "d1#0"


def test_en_correccion_los_fragmentos_siguen_en_el_prompt():
    PROMPTS.clear()

    async def buscar(**kw):
        return [R1]

    asyncio.run(redactor.run_redactor(_state([{"doc_id": "d1"}], buscar, feedback=["mejora"], draft_text="x")))
    assert "[F1]" in PROMPTS[0]


def test_sin_sources_no_hay_fragmentos_ni_busqueda():
    async def buscar(**kw):
        raise AssertionError("no debe buscar")

    out = asyncio.run(redactor.run_redactor(_state([], buscar)))
    assert out["citation_map"] == {}


def test_puente_a_save_citation_map_conserva_las_funciones_de_t23_2():
    mapa = c.assign_cite_ids([R1])
    out = c.extract_citations("Dato [F1]. Inventado [F5].", mapa)
    ins = c.to_citation_inputs(out["citations"])
    assert [i.citation_key for i in ins] == ["F1", "F5"]
    assert ins[0].doc_id == "d1" and ins[0].excerpt.startswith("La metformina")
    assert ins[1].doc_id is None and ins[1].excerpt == ""
    for nombre in ("save_citation_map", "get_citation_map", "current_citation_map", "confirm_citation"):
        assert callable(getattr(c, nombre))
