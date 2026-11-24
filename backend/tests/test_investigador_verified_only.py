"""Investigador: solo biblioteca verificada y abstención (SPEC-034 / T22.5 / AC5, AC7).

Sin red: el RAG y el LLM se sustituyen por dobles; la biblioteca es la real (SQLite).
"""
import os
import shutil
import sys
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

TEST_DB_PATH = (ROOT_DIR / "tests" / "test_investigador_verified_only.db").resolve()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

import app.platform.llm as llm_module  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import ProjectModel, UserModel, UserRole  # noqa: E402
from app.modules.agents.adapters import investigador, redactor  # noqa: E402
from app.modules.agents.domain import alejandria  # noqa: E402
from app.platform import explainability, library  # noqa: E402
from app.platform.capabilities.literature.research import (  # noqa: E402
    DEFAULT_MIN_SOURCES, ResearchConfig, ResearchConfigError, parse_research,
)
from app.platform.engine.graph import GraphSpec, build_graph  # noqa: E402
from app.platform.engine.routing import FIN, make_halt_router  # noqa: E402
from app.platform.projects import loader  # noqa: E402


# ── Entorno ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def mundo():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        user = UserModel(
            email="autora@ejemplo.com", hashed_password=hash_password("x" * 12),
            full_name="Autora", role=UserRole.REDACTOR, is_active=True,
        )
        p1, p2 = ProjectModel(name="P1"), ProjectModel(name="P2")
        session.add_all([user, p1, p2])
        await session.commit()
        for obj in (user, p1, p2):
            await session.refresh(obj)
        ids = {"user": user.id, "p1": p1.id, "p2": p2.id}
    yield ids
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _doc(project, n, *, verified="system", curation="accepted", doi=True, user=None,
               source_db="openalex"):
    """Alta de un documento de la biblioteca ligado al `doc_id` «rag-<n>» del RAG."""
    async with AsyncSessionLocal() as session:
        doc = await library.add_document(
            session, project, doc_id=f"rag-{n}", title=f"Paper {n}",
            authors=[f"Autor {n}", "Otra Autora"], year=2020 + n, journal="Nature",
            doi=f"10.1000/p{n}" if doi else None, source_db=source_db,
            url=f"https://doi.org/10.1000/p{n}" if doi else None,
        )
        if curation != "candidate":
            await library.set_curation(session, project, doc.id, curation)
        if verified == "system":
            await library.mark_verified(session, project, doc.id, "doi_resolved")
        elif verified == "author":
            await library.mark_verified(session, project, doc.id, "author_supplied", verified_by=user)
    return doc


def _hit(n, score=0.8, text=None):
    return {"doc_id": f"rag-{n}", "text": text or f"hallazgo del paper {n}", "filename": f"p{n}.pdf",
            "doc_title": f"Paper {n}", "doc_authors": "", "score": score}


@pytest.fixture
def entorno(monkeypatch):
    """RAG y LLM de mentira. Devuelve el estado de lo que se pidió."""
    # `llm`: solo la síntesis (lo que no debe ocurrir sin evidencia). Las sub-preguntas de
    # sección (T22.17) piden al modelo solo título y enfoque y se anotan aparte.
    visto = {"rag": [], "llm": [], "llm_subpreguntas": []}
    resultados = {"hits": []}

    async def rag(**kw):
        visto["rag"].append(kw)
        return list(resultados["hits"])

    async def backend(*_a, **_k):
        return "test"

    async def llm(prompt, **kw):
        if prompt.startswith("Eres un bibliotecario"):
            visto["llm_subpreguntas"].append(prompt)
            return "no es json"
        visto["llm"].append(prompt)
        return "resumen " + "palabra " * 40

    monkeypatch.setattr(investigador, "semantic_search_results", rag)
    monkeypatch.setattr(investigador, "get_rag_backend", backend)
    monkeypatch.setattr(llm_module, "call_llm", llm)
    monkeypatch.setattr(settings, "RAG_SCORE_THRESHOLD", 0.3, raising=False)
    visto["resultados"] = resultados
    return visto


def _estado(project, logs=None, **extra):
    state = {
        "article_id": uuid4(), "project_id": project, "title": "Aprendizaje por refuerzo",
        "keywords": ["curriculum"], "agent_settings": {},
        "_log": (lambda m, level="info": logs.append((level, m))) if logs is not None else None,
    }
    state.update(extra)
    return state


# ── min_sources: plantilla, validación, no reducible ────────────────────────

def test_min_sources_por_defecto_es_3_y_la_plantilla_lo_declara():
    assert DEFAULT_MIN_SOURCES == 3
    assert ResearchConfig().min_sources == 3
    assert parse_research(None).min_sources == 3
    assert parse_research({"sources": ["openalex"]}).min_sources == 3
    assert alejandria.package().research.min_sources == 3


@pytest.mark.parametrize("valor", [0, -1, 2.5, "3", True, [3], {"n": 3}])
def test_min_sources_invalido_se_rechaza_al_cargar(valor):
    with pytest.raises(ResearchConfigError):
        parse_research({"min_sources": valor})


def test_min_sources_valido_se_respeta():
    assert parse_research({"min_sources": 5}).min_sources == 5
    assert parse_research({"sources": ["crossref"], "min_sources": 1}).min_sources == 1


def test_una_plantilla_con_min_sources_invalido_no_carga(tmp_path):
    origen = ROOT_DIR / "projects" / "alejandria-magazine"
    destino = tmp_path / "alejandria-magazine"
    shutil.copytree(origen, destino)
    plantilla = destino / "template.yaml"
    texto = plantilla.read_text(encoding="utf-8")
    assert "min_sources: 3" in texto
    plantilla.write_text(texto.replace("min_sources: 3", "min_sources: 0"), encoding="utf-8")
    with pytest.raises(loader.TemplateError):
        loader.load_from(destino)
    # Y con un valor válido distinto, carga y se refleja.
    plantilla.write_text(texto.replace("min_sources: 3", "min_sources: 4"), encoding="utf-8")
    assert loader.load_from(destino).research.min_sources == 4


@pytest.mark.asyncio
async def test_el_autor_no_puede_bajar_min_sources_desde_los_ajustes(mundo, entorno):
    p = mundo["p1"]
    for n in (1, 2):
        await _doc(p, n)
    entorno["resultados"]["hits"] = [_hit(1), _hit(2)]
    logs = []
    out = await investigador.run_investigador(_estado(
        p, logs, agent_settings={"investigador": {"min_sources": 1}},
    ))
    assert out["abstained"] is True            # 2 < 3: el ajuste del autor no cuenta
    assert out["abstention"]["min_sources"] == 3
    assert any("min_sources" in m for _lvl, m in logs)


# ── AC5: solo DOI verificado en `sources` ───────────────────────────────────

@pytest.mark.asyncio
async def test_ac5_solo_los_verificados_entran_en_sources(mundo, entorno):
    p = mundo["p1"]
    for n in (1, 2, 3):
        await _doc(p, n)
    await _doc(p, 4, verified=None)                       # aceptado pero sin verificar
    entorno["resultados"]["hits"] = [_hit(n) for n in (1, 2, 3, 4)]
    out = await investigador.run_investigador(_estado(p))
    assert not out.get("abstained")
    assert {s["doc_id"] for s in out["sources"]} == {"rag-1", "rag-2", "rag-3"}
    assert all(s["doi"] for s in out["sources"])
    # La síntesis ya no es una «fuente».
    assert not any(str(s.get("url", "")).startswith("synthesis://") for s in out["sources"])
    # El no verificado no aparece citado ni en el texto que recibe el Redactor...
    assert "[Fuente: Paper 4]" not in out["research_data"]
    assert "Paper 4" not in out["research_data"].split("---")[0]
    # ...pero sí informó la síntesis, marcado como no citable.
    assert "CONTEXTO NO CITABLE" in entorno["llm"][0]
    assert "hallazgo del paper 4" in entorno["llm"][0]
    assert "Paper 4" not in entorno["llm"][0]


@pytest.mark.asyncio
async def test_ac5_el_doi_aportado_por_el_autor_cuenta_como_verificado(mundo, entorno):
    p = mundo["p1"]
    await _doc(p, 1)
    await _doc(p, 2)
    await _doc(p, 3, verified="author", user=mundo["user"])
    entorno["resultados"]["hits"] = [_hit(n) for n in (1, 2, 3)]
    out = await investigador.run_investigador(_estado(p))
    assert not out.get("abstained")
    por_doc = {s["doc_id"]: s for s in out["sources"]}
    assert por_doc["rag-3"]["doi_verification"] == "author_supplied"
    assert por_doc["rag-1"]["doi_verification"] == "doi_resolved"


@pytest.mark.asyncio
async def test_ac5_no_hay_excepcion_para_documento_interno(mundo, entorno):
    """Sin DOI verificado, un documento «interno» solo es contexto (ADR-0011)."""
    p = mundo["p1"]
    await _doc(p, 1)
    await _doc(p, 2)
    await _doc(p, 3, verified=None, doi=False, source_db="manual")   # interno, sin DOI
    entorno["resultados"]["hits"] = [_hit(n) for n in (1, 2, 3)]
    out = await investigador.run_investigador(_estado(p))
    assert out["abstained"] is True
    assert out["sources"] == []
    assert out["abstention"]["verified_sources"] == 2
    assert out["abstention"]["context_only_documents"] == 1


@pytest.mark.asyncio
async def test_ac5_candidato_verificado_pero_no_aceptado_no_es_citable(mundo, entorno):
    p = mundo["p1"]
    await _doc(p, 1)
    await _doc(p, 2)
    await _doc(p, 3, curation="candidate")          # verificado, sin aceptar
    entorno["resultados"]["hits"] = [_hit(n) for n in (1, 2, 3)]
    out = await investigador.run_investigador(_estado(p))
    assert out["abstained"] is True and out["abstention"]["verified_sources"] == 2


@pytest.mark.asyncio
async def test_un_documento_descartado_no_se_usa_ni_como_contexto(mundo, entorno):
    p = mundo["p1"]
    for n in (1, 2, 3):
        await _doc(p, n)
    await _doc(p, 4, curation="discarded", verified=None)
    entorno["resultados"]["hits"] = [_hit(n) for n in (1, 2, 3, 4)]
    await investigador.run_investigador(_estado(p))
    assert "hallazgo del paper 4" not in entorno["llm"][0]


# ── Transición: documentos del RAG sin fila de biblioteca ───────────────────

@pytest.mark.asyncio
async def test_documentos_sin_fila_de_biblioteca_son_solo_contexto_y_no_rompen(mundo, entorno):
    """Proyectos existentes: el RAG tiene documentos y `library_documents` está vacía."""
    p = mundo["p1"]
    entorno["resultados"]["hits"] = [_hit(n) for n in (1, 2, 3, 4)]
    logs = []
    out = await investigador.run_investigador(_estado(p, logs))
    assert out["abstained"] is True
    assert out["sources"] == [] and out["research_data"] == ""
    assert out["abstention"]["verified_sources"] == 0
    assert out["abstention"]["context_only_documents"] == 4
    # El mensaje dice exactamente qué hacer y qué documentos son.
    msg = out["abstention"]["message"]
    assert "Paper 1" in msg and "DOI" in msg and "Qué hacer" in msg
    assert any(lvl == "warning" and "se ha abstenido" in m for lvl, m in logs)
    assert entorno["llm"] == []


@pytest.mark.asyncio
async def test_sin_proyecto_todo_es_contexto_y_se_abstiene(entorno):
    entorno["resultados"]["hits"] = [_hit(1), _hit(2), _hit(3)]
    out = await investigador.run_investigador(_estado(None))
    assert out["abstained"] is True and out["sources"] == []


@pytest.mark.asyncio
async def test_la_biblioteca_no_cruza_proyectos(mundo, entorno):
    """Tres documentos verificados en P2 no hacen citable el mismo `doc_id` en P1."""
    for n in (1, 2, 3):
        await _doc(mundo["p2"], n)
    entorno["resultados"]["hits"] = [_hit(n) for n in (1, 2, 3)]
    fuera = await investigador.run_investigador(_estado(mundo["p1"]))
    assert fuera["abstained"] is True and fuera["abstention"]["verified_sources"] == 0
    dentro = await investigador.run_investigador(_estado(mundo["p2"]))
    assert not dentro.get("abstained") and len(dentro["sources"]) == 3


# ── AC7: abstención ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ac7_sin_resultados_no_sintetiza_desde_conocimiento_parametrico(mundo, entorno):
    logs = []
    out = await investigador.run_investigador(_estado(mundo["p1"], logs))
    assert out["abstained"] is True
    assert entorno["llm"] == []                     # no se llamó al modelo
    assert "Contexto base" not in str(out) and "conocimiento propio" not in str(out)
    assert out["research_data"] == "" and out["sources"] == []
    assert "umbral de similitud" in out["abstention"]["message"]


@pytest.mark.asyncio
async def test_ac7_el_rag_caido_se_dice_y_no_se_inventa(mundo, entorno, monkeypatch):
    async def roto(**_kw):
        raise RuntimeError("qdrant caído")

    monkeypatch.setattr(investigador, "semantic_search_results", roto)
    out = await investigador.run_investigador(_estado(mundo["p1"]))
    assert out["abstained"] is True and out["abstention"]["rag_unavailable"] is True
    assert "no estuvo disponible" in out["abstention"]["message"]
    assert entorno["llm"] == []


@pytest.mark.asyncio
async def test_ac7_el_umbral_de_similitud_decide_quien_cuenta(mundo, entorno):
    p = mundo["p1"]
    for n in (1, 2, 3):
        await _doc(p, n)
    # El 3 está verificado pero por debajo del umbral (0.3): no cuenta.
    entorno["resultados"]["hits"] = [_hit(1, 0.9), _hit(2, 0.5), _hit(3, 0.1)]
    out = await investigador.run_investigador(_estado(p))
    assert out["abstained"] is True and out["abstention"]["verified_sources"] == 2
    assert out["abstention"]["similarity_threshold"] == 0.3
    # Un fragmento sin puntuación tampoco se demuestra por encima del umbral...
    sin_score = _hit(3)
    sin_score.pop("score")
    entorno["resultados"]["hits"] = [_hit(1), _hit(2), sin_score]
    assert (await investigador.run_investigador(_estado(p)))["abstained"] is True
    # ...salvo que el autor eligiera esos documentos (misma regla que T22.6).
    sel = {"investigador": {"rag_doc_ids": ["rag-1", "rag-2", "rag-3"]}}
    out = await investigador.run_investigador(_estado(p, agent_settings=sel))
    assert not out.get("abstained")


@pytest.mark.asyncio
async def test_ac7_justo_en_n_investiga(mundo, entorno):
    p = mundo["p1"]
    for n in (1, 2, 3):
        await _doc(p, n)
    entorno["resultados"]["hits"] = [_hit(n) for n in (1, 2, 3)]
    out = await investigador.run_investigador(_estado(p))
    assert not out.get("abstained") and len(out["sources"]) == 3
    assert out["research_data"].startswith("FUENTES CITABLES")
    assert "[Síntesis]" in out["research_data"]


@pytest.mark.asyncio
async def test_el_mensaje_al_autor_es_accionable(mundo, entorno):
    p = mundo["p1"]
    await _doc(p, 1)
    entorno["resultados"]["hits"] = [_hit(1), _hit(2)]    # el 2 no tiene fila
    out = await investigador.run_investigador(_estado(p))
    msg = out["abstention"]["message"]
    assert "1 fuente(s) citable(s)" in msg and "al menos 3" in msg
    assert "Paper 2" in msg and "no son citables" in msg
    # T22.13: dice cómo resolverlo: verificar el DOI **o** declararlo «aportado por el autor».
    assert "verifica su DOI" in msg and "aportado por el autor" in msg and "vuelve a ejecutar" in msg


# ── Traza y motor ───────────────────────────────────────────────────────────

def test_la_abstencion_se_declara_en_la_traza():
    salida = {"abstained": True, "abstention": {
        "reason": "insufficient_verified_sources", "message": "faltan fuentes",
        "verified_sources": 1, "min_sources": 3, "similarity_threshold": 0.3,
        "context_only_documents": 2,
    }}
    decision = explainability.decision_of(salida)
    assert decision["abstained"] is True
    assert decision["verified_sources"] == 1 and decision["min_sources"] == 3
    assert explainability.rationale_of(salida) == "faltan fuentes"
    # Un paso normal no se confunde con una abstención.
    assert explainability.decision_of({"research_data": "x"}) is None


def test_el_router_de_parada_respeta_la_abstencion():
    router = make_halt_router("redactor")
    assert router({"abstained": True}) == FIN
    assert router({"abstained": False}) == "redactor"
    assert router({}) == "redactor"


@pytest.mark.asyncio
async def test_el_motor_detiene_el_flujo_tras_una_abstencion():
    from app.modules.agents.domain.entities import AgentState

    corridos = []

    def factory(nombre):
        async def nodo(state):
            corridos.append(nombre)
            if nombre == "uno":
                return {"abstained": True, "abstention": {"message": "m"}}
            return {}
        return nodo

    grafo = build_graph(GraphSpec(sequence=("uno", "dos", "tres"), loops=()), factory, AgentState)
    final = await grafo.ainvoke({"title": "t"})
    assert corridos == ["uno"]
    assert final["abstained"] is True

    corridos.clear()

    def factory_ok(nombre):
        async def nodo(state):
            corridos.append(nombre)
            return {}
        return nodo

    grafo = build_graph(GraphSpec(sequence=("uno", "dos", "tres"), loops=()), factory_ok, AgentState)
    await grafo.ainvoke({"title": "t"})
    assert corridos == ["uno", "dos", "tres"]


@pytest.mark.asyncio
async def test_el_wrapper_publica_el_evento_y_traza_la_decision(monkeypatch):
    from app.modules.agents.application import use_cases as orquestador

    eventos, pasos = [], []

    async def _start(*_a, **_k):
        return uuid4()

    async def _end(*_a, **_k):
        return None

    async def _step(**kw):
        pasos.append(kw)

    monkeypatch.setattr(orquestador, "log_run_start", _start)
    monkeypatch.setattr(orquestador, "log_run_end", _end)
    monkeypatch.setattr(orquestador, "log_run_step", _step)
    monkeypatch.setattr(orquestador, "publish_event", lambda _id, ev: eventos.append(ev))

    async def runner(_state):
        return {"research_data": "", "sources": [], "abstained": True, "abstention": {
            "message": "faltan fuentes", "verified_sources": 1, "min_sources": 3,
            "reason": "insufficient_verified_sources",
        }}

    nodo = orquestador.make_node_wrapper("investigador", runner)
    await nodo({"article_id": uuid4(), "author_id": uuid4(), "title": "t", "keywords": [],
                "agent_settings": {}})
    abst = [e for e in eventos if e["type"] == "abstained"]
    assert abst and abst[0]["message"] == "faltan fuentes" and abst[0]["min_sources"] == 3
    assert pasos[0]["decision"]["abstained"] is True
    assert pasos[0]["rationale"] == "faltan fuentes"


# ── El Redactor no añade fuentes propias (AC5) ──────────────────────────────

async def _correr_redactor(monkeypatch, state):
    visto = {"rag": [], "prompt": ""}

    async def rag(**kw):
        visto["rag"].append(kw)
        return [{"doc_id": d, "chunk_index": 0, "filename": "f.pdf",
                 "text": "fragmento extra de una fuente citable"} for d in kw["doc_ids"]]

    async def stream(prompt, **_kw):
        visto["prompt"] = prompt
        yield "Borrador " * 20

    monkeypatch.setattr(redactor, "semantic_search_results", rag)
    monkeypatch.setattr(redactor, "call_llm_stream", stream)
    base = {"title": "T", "keywords": ["k"], "agent_settings": {}, "feedback": [], "_log": None}
    base.update(state)
    await redactor.run_redactor(base)
    return visto


@pytest.mark.asyncio
async def test_el_redactor_solo_amplia_desde_las_fuentes_citables(monkeypatch):
    visto = await _correr_redactor(monkeypatch, {
        "research_data": "FUENTES CITABLES: ...", "project_id": uuid4(),
        "sources": [{"doc_id": "rag-1", "title": "A"}, {"doc_id": "rag-2", "title": "B"}],
    })
    assert len(visto["rag"]) == 1
    # El filtro es por documento: nada fuera de `sources` puede entrar.
    assert visto["rag"][0]["doc_ids"] == ["rag-1", "rag-2"]
    assert "fragmento extra de una fuente citable" in visto["prompt"]


@pytest.mark.asyncio
async def test_el_redactor_sin_fuentes_no_consulta_el_rag_por_su_cuenta(monkeypatch):
    visto = await _correr_redactor(monkeypatch, {"research_data": "", "sources": [], "project_id": uuid4()})
    assert visto["rag"] == []
    assert "fragmento extra" not in visto["prompt"]


@pytest.mark.asyncio
async def test_la_seleccion_del_autor_no_amplia_mas_alla_de_sources(monkeypatch):
    visto = await _correr_redactor(monkeypatch, {
        "research_data": "x", "project_id": uuid4(),
        "sources": [{"doc_id": "rag-1"}],
        "agent_settings": {"redactor": {"rag_doc_ids": ["rag-1", "rag-ajeno"]}},
    })
    assert visto["rag"][0]["doc_ids"] == ["rag-1"]


def test_los_prompts_del_redactor_distinguen_citable_de_contexto():
    assert "SOLO las fuentes listadas como citables" in redactor._DEFAULT_TEMPLATE_ES
    assert "ONLY the sources listed as citable" in redactor._DEFAULT_TEMPLATE_EN


# ── Perfil alineado con el código ───────────────────────────────────────────

def test_el_perfil_no_promete_lo_que_el_codigo_no_hace():
    ruta = ROOT_DIR / "projects" / "alejandria-magazine" / "agents" / "investigador.agent.md"
    texto = ruta.read_text(encoding="utf-8")
    for falso in ("EuropePMC", "datos simulados", "Consulta a APIs científicas públicas"):
        assert falso not in texto, falso
    for verdadero in ("DOI verificado", "se abstiene", "research.min_sources"):
        assert verdadero in texto, verdadero
    # La plantilla y todos los perfiles siguen cargando (los localiza el loader).
    paquete = alejandria.package()
    assert set(paquete.profiles) >= {"investigador", "redactor", "revisor", "formateador", "publicador"}
    assert all(Path(p).is_file() for p in paquete.profiles.values())


# ── EDD: las métricas nuevas muerden (DoD de evaluación) ────────────────────

@pytest.mark.asyncio
async def test_edd_golden_del_investigador_pasa_con_las_metricas_nuevas():
    from evals.agent_behavior import runner

    informe = await runner.run("investigador-golden", mode="replay")
    assert informe.passed
    puntuaciones = informe.scores()
    assert puntuaciones["source_verification"] == 100.0
    assert puntuaciones["abstention"] == 100.0


@pytest.mark.asyncio
async def test_edd_las_regresiones_de_t22_5_fallan_por_su_metrica():
    from evals.agent_behavior import runner

    informe = await runner.run("investigador-regressions", mode="replay")
    por_caso = {c.case_id: {m.name: m for m in c.metrics} for c in informe.cases}
    assert por_caso["cita-fuente-sin-verificar"]["source_verification"].passed is False
    assert por_caso["sintesis-sin-evidencia"]["abstention"].passed is False
