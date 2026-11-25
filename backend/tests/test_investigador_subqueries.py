"""Investigador: recuperación por sub-preguntas de sección (SPEC-034 / T22.17 / AC18).

Reutiliza el mundo y los dobles de `test_investigador_verified_only` (sin red).
"""
import asyncio
import json
import shutil

import pytest

from tests.test_investigador_verified_only import (  # noqa: F401
    ROOT_DIR, _doc, _estado, _hit, entorno, mundo,
)
import app.platform.llm as llm_module
from app.modules.agents.adapters import investigador, redactor
from app.modules.agents.domain import alejandria
from app.platform import explainability
from app.platform.capabilities import subqueries as subq
from app.platform.capabilities.literature.research import (
    DEFAULT_MAX_SUBQUERIES, ResearchConfig, ResearchConfigError, parse_research,
)
from app.platform.projects import loader


# ── max_subqueries: plantilla, validación, no modificable ───────────────────

def test_max_subqueries_por_defecto_es_6_y_la_plantilla_lo_declara():
    assert DEFAULT_MAX_SUBQUERIES == 6
    assert ResearchConfig().max_subqueries == 6
    assert parse_research(None).max_subqueries == 6
    assert parse_research({"sources": ["crossref"]}).max_subqueries == 6
    assert alejandria.package().research.max_subqueries == 6


@pytest.mark.parametrize("valor", [0, -1, 2.5, "6", True, []])
def test_max_subqueries_invalido_se_rechaza_al_cargar(valor):
    with pytest.raises(ResearchConfigError, match="max_subqueries"):
        parse_research({"max_subqueries": valor})


def test_max_subqueries_valido_se_respeta():
    assert parse_research({"max_subqueries": 4}).max_subqueries == 4
    assert parse_research({"sources": ["crossref"], "max_subqueries": 1}).max_subqueries == 1


def test_una_plantilla_con_max_subqueries_invalido_no_carga(tmp_path):
    destino = tmp_path / "alejandria-magazine"
    shutil.copytree(ROOT_DIR / "projects" / "alejandria-magazine", destino)
    plantilla = destino / "template.yaml"
    texto = plantilla.read_text(encoding="utf-8")
    assert "max_subqueries: 6" in texto
    plantilla.write_text(texto.replace("max_subqueries: 6", "max_subqueries: 0"), encoding="utf-8")
    with pytest.raises(loader.TemplateError):
        loader.load_from(destino)
    plantilla.write_text(texto.replace("max_subqueries: 6", "max_subqueries: 3"), encoding="utf-8")
    assert loader.load_from(destino).research.max_subqueries == 3


# ── Plan de sub-preguntas (puro) ────────────────────────────────────────────

def test_el_prompt_solo_lleva_titulo_y_enfoque():
    p = subq.build_prompt("Titulo X", "Enfoque Y", 6)
    assert "Titulo X" in p and "Enfoque Y" in p and "máximo 6" in p


def test_sin_respuesta_utilizable_quedan_las_deterministas_una_por_seccion():
    for crudo in (None, "", "no es json", "[1, 2]", '[{"section": "otra", "question": "x"}]'):
        plan = subq.plan("Mi título", crudo, 6)
        assert [q["section"] for q in plan] == list(subq.SECCIONES)
        assert all("Mi título" in q["question"] for q in plan)
        assert [q["id"] for q in plan] == ["q1", "q2", "q3", "q4"]


def test_el_tope_acota_y_prioriza_una_por_seccion():
    crudo = json.dumps([
        {"section": "results", "question": f"r{i}"} for i in range(10)
    ] + [{"section": "method", "question": "m1"}])
    plan = subq.plan("T", crudo, 6)
    assert len(plan) == 6
    assert {q["section"] for q in plan} == set(subq.SECCIONES)       # todas las secciones primero
    assert len(subq.plan("T", crudo, 1)) == 1
    assert len(subq.plan("T", crudo, 100)) == 4 + 9                  # nunca más que lo propuesto


def test_la_respuesta_del_modelo_se_trata_como_no_confiable():
    crudo = 'Aquí tienes: [{"section": "PROBLEM", "question": "  ¿a   qué?  "}, {"section": "method"}, 7]'
    plan = subq.plan("T", crudo, 6)
    assert plan[0]["section"] == "problem" and plan[0]["question"] == "¿a qué?"


def test_cobertura_por_seccion():
    plan = subq.plan("T", None, 6)
    frs = [{"subqueries": ["q1"]}, {"subqueries": ["q1", "q3"]}, {"subqueries": ["title"]}]
    cob = {c["section"]: c for c in subq.coverage(plan, frs)}
    assert cob["problem"]["covered"] and cob["problem"]["fragments"] == 2
    assert cob["results"]["covered"] and not cob["method"]["covered"]
    assert not cob["limitations"]["covered"]                  # lo del título no cubre secciones


def test_aviso_del_redactor_lista_solo_los_huecos():
    cob = [{"section": "method", "label": "método", "covered": False},
           {"section": "problem", "label": "problema", "covered": True}]
    assert "método" in subq.render_gaps(cob) and "problema" not in subq.render_gaps(cob)
    assert "NO rellenes" in subq.render_gaps(cob)
    assert "Do NOT fill" in subq.render_gaps(cob, "en")
    assert subq.render_gaps([{"covered": True}]) == ""


# ── Investigador ────────────────────────────────────────────────────────────

def _rag_por_consulta(monkeypatch, entorno, respuestas):
    """RAG que responde según la consulta: `respuestas` mapea fragmento-de-consulta -> hits."""
    async def rag(**kw):
        entorno["rag"].append(kw)
        for clave, hits in respuestas.items():
            if clave in kw["query"]:
                return [dict(h) for h in hits]
        return []
    monkeypatch.setattr(investigador, "semantic_search_results", rag)


@pytest.mark.asyncio
async def test_recupera_por_subpregunta_y_cada_fragmento_declara_la_suya(mundo, entorno, monkeypatch):
    p = mundo["p1"]
    for n in (1, 2, 3):
        await _doc(p, n)
    # Las sub-preguntas también llevan el título: las palabras de sección van primero.
    _rag_por_consulta(monkeypatch, entorno, {
        "problema": [_hit(1, text="el problema de la exploración en el aprendizaje")],
        "método": [_hit(2, text="el método usa currículos adaptativos de tareas")],
        "resultados": [_hit(3, text="los resultados mejoran un veinte por ciento")],
        "limitaciones": [_hit(3, text="las limitaciones incluyen el coste de cómputo")],
        "Aprendizaje": [_hit(1, text="el problema de la exploración en el aprendizaje")],
    })
    out = await investigador.run_investigador(_estado(p, context_description="enfoque del autor"))
    assert not out.get("abstained")
    # Título + una consulta por sub-pregunta.
    cobertura = out["research_coverage"]
    assert len(entorno["rag"]) == 1 + len(cobertura["subqueries"]) == 5
    assert cobertura["uncovered_sections"] == []
    # El fragmento declara de qué sub-pregunta viene.
    assert "[Sub-pregunta q2: método]" in out["research_data"]
    assert "[Sub-pregunta q3: resultados]" in out["research_data"]
    # Solo título y enfoque del autor llegan al modelo que propone.
    assert len(entorno["llm_subpreguntas"]) == 1
    propuesta = entorno["llm_subpreguntas"][0]
    assert "Aprendizaje por refuerzo" in propuesta and "enfoque del autor" in propuesta
    assert "método usa currículos" not in propuesta


@pytest.mark.asyncio
async def test_seccion_sin_evidencia_sustantiva_queda_sin_cobertura_en_la_traza(mundo, entorno, monkeypatch):
    p = mundo["p1"]
    for n in (1, 2, 3):
        await _doc(p, n)
    ref = _hit(3, text="Smith J. (2019) Deep learning for things. Nature 12, 1-10.")
    ref["section"] = "references"
    _rag_por_consulta(monkeypatch, entorno, {
        "problema": [_hit(1, text="el problema de la exploración en el aprendizaje")],
        "método": [_hit(2, text="el método usa currículos adaptativos de tareas")],
        "resultados": [ref],                       # solo bibliografía: no es evidencia
        "limitaciones": [],
        "Aprendizaje": [_hit(1), _hit(2), _hit(3)],   # el título trae material, pero no cubre secciones
    })
    out = await investigador.run_investigador(_estado(p))
    assert not out.get("abstained")
    assert out["research_coverage"]["uncovered_sections"] == ["results", "limitations"]
    # Va a la traza (T9.1): la decisión del paso lleva sub-preguntas y secciones sin cobertura.
    decision = explainability.decision_of(out)
    assert decision["uncovered_sections"] == ["results", "limitations"]
    assert [q["id"] for q in decision["subqueries"]] == ["q1", "q2", "q3", "q4"]
    assert all("question" in q and "substantive_fragments" in q for q in decision["subqueries"])
    # La referencia no entra como material.
    assert "Deep learning for things" not in out["research_data"]


@pytest.mark.asyncio
async def test_el_tope_lo_fija_la_plantilla_no_el_autor(mundo, entorno, monkeypatch):
    p = mundo["p1"]
    for n in (1, 2, 3):
        await _doc(p, n)
    entorno["resultados"]["hits"] = [_hit(1), _hit(2), _hit(3)]
    logs = []
    out = await investigador.run_investigador(_estado(
        p, logs, agent_settings={"investigador": {"max_subqueries": 1}}))
    assert len(out["research_coverage"]["subqueries"]) == 4      # el 1 del autor no cuenta
    assert any("max_subqueries" in m for _l, m in logs)
    monkeypatch.setattr(investigador, "_max_subqueries", lambda: 2)
    out = await investigador.run_investigador(_estado(p))
    assert len(out["research_coverage"]["subqueries"]) == 2


@pytest.mark.asyncio
async def test_sin_respuesta_del_modelo_se_usan_las_deterministas(mundo, entorno, monkeypatch):
    p = mundo["p1"]
    for n in (1, 2, 3):
        await _doc(p, n)
    entorno["resultados"]["hits"] = [_hit(1), _hit(2), _hit(3)]

    async def roto(prompt, **kw):
        if prompt.startswith("Eres un bibliotecario"):
            raise RuntimeError("modelo caído")
        return "resumen " + "palabra " * 40
    monkeypatch.setattr(llm_module, "call_llm", roto)
    out = await investigador.run_investigador(_estado(p))
    assert not out.get("abstained")
    assert len(out["research_coverage"]["subqueries"]) == 4


@pytest.mark.asyncio
async def test_la_abstencion_conserva_las_subpreguntas_en_la_traza(mundo, entorno):
    p = mundo["p1"]
    await _doc(p, 1)
    entorno["resultados"]["hits"] = [_hit(1)]
    out = await investigador.run_investigador(_estado(p))
    assert out["abstained"] is True
    decision = explainability.decision_of(out)
    assert decision["abstained"] is True and len(decision["subqueries"]) == 4


def test_el_investigador_resuelve_modelo_y_temperatura_con_la_cascada_en_la_propuesta():
    fuente = (ROOT_DIR / "app" / "modules" / "agents" / "adapters" / "investigador.py").read_text(encoding="utf-8")
    bloque = fuente.split("async def _proponer_subpreguntas")[1].split("def _ordenar_por_subpregunta")[0]
    assert "resolve_agent_model" in bloque and "resolve_agent_temperature" in bloque
    assert "temperature=temperature" in bloque and "model=model" in bloque


# ── Redactor ────────────────────────────────────────────────────────────────

def test_el_redactor_recibe_las_secciones_sin_cobertura_y_no_las_rellena():
    from app.platform.capabilities import binding
    prompts = []

    async def llm(prompt, **kw):
        prompts.append(prompt)
        __import__("app.platform.llm", fromlist=["x"])._anotar_motivo_parada("stop")  # el proveedor declara fin natural
        yield "## Introducción\n\nTexto.\n\n## Metodología\n\nTexto.\n\n## Resultados\n\nTexto.\n\n## Discusión\n\nTexto."

    async def buscar(**kw):
        return []

    cobertura = {"coverage": [
        {"section": "results", "label": "resultados", "covered": False},
        {"section": "problem", "label": "problema", "covered": True},
    ]}
    state = {
        "title": "T", "keywords": [], "sources": [], "research_data": "ctx", "agent_settings": {},
        "article_id": None, "research_coverage": cobertura,
        binding.CLAVE_ESTADO: binding.CapabilityBundle({"rag_results": buscar, "llm_stream": llm}),
    }
    asyncio.run(redactor.run_redactor(state))
    assert "no tienen contenido sustantivo sobre: resultados" in prompts[0]
    assert "NO rellenes" in prompts[0]
    # Sin huecos, no hay aviso.
    prompts.clear()
    state["research_coverage"] = {"coverage": [{"section": "problem", "label": "problema", "covered": True}]}
    asyncio.run(redactor.run_redactor(state))
    assert "NO rellenes esas partes" not in prompts[0]
