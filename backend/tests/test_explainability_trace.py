"""Traza de explicabilidad por paso (SPEC-014 / T9.1 / AC1).

AC1: al terminar (o cancelarse) una ejecución existe una traza persistida con un
registro **por paso de agente** que incluye agente, modelo y parámetros, resumen
de entrada/salida, **fuentes RAG citadas** (`doc_id`, `chunk_ids`, score), tokens
in/out, latencia y —cuando aplique— decisión y *rationale*.

Lo que había: `agent_runs` registraba **que** un agente corrió, con su entrada y
su salida. No registraba por qué salió lo que salió — qué se recuperó del RAG y
con qué puntuación, con qué modelo, cuánto costó, ni con qué criterio el revisor
rechazó un borrador. Eso solo vivía en logs de texto con emojis y en eventos SSE,
que son efímeros por definición.

Tres de esos datos no están donde se escribe el paso: los tokens los conoce el
proveedor del LLM, las fuentes las conoce la capacidad de RAG, y el agente que la
llama se queda con el texto ya montado. Por eso se recogen con variables de
contexto — y por eso los tests de abajo comprueban que el recorrido completo
funciona, no solo que la tabla existe.
"""
import os
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

TEST_DB_PATH = (ROOT_DIR / "tests" / "test_explain.db").resolve()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.models import AgentRunStepModel  # noqa: E402
from app.modules.agents.adapters import investigador as adapter_investigador  # noqa: E402
from app.modules.agents.adapters import redactor as adapter_redactor  # noqa: E402
from app.modules.agents.adapters import revisor as adapter_revisor  # noqa: E402
from app.modules.agents.application import use_cases as orquestador  # noqa: E402
from app.platform import explainability as ex  # noqa: E402


# ── El recolector ───────────────────────────────────────────────────────────

def test_los_tokens_se_suman_entre_llamadas():
    """Un paso puede llamar al LLM varias veces: el redactor amplía si se queda corto."""
    with ex.collecting() as acumulador:
        ex.record_tokens(100, 50)
        ex.record_tokens(20, 10)
    assert (acumulador.tokens_in, acumulador.tokens_out) == (120, 60)


def test_las_fuentes_se_agrupan_por_documento():
    """La pregunta es «¿de qué documentos salió esto?», no «¿qué fragmentos?»."""
    with ex.collecting() as acumulador:
        ex.record_rag_hits("col", [
            {"doc_id": "d1", "chunk_id": 1, "score": 0.80, "doc_title": "Uno", "doc_authors": "A"},
            {"doc_id": "d1", "chunk_id": 2, "score": 0.95},
            {"doc_id": "d2", "chunk_id": 9, "score": 0.40},
        ])
    por_doc = {f["doc_id"]: f for f in acumulador.rag_sources}
    assert por_doc["d1"]["chunk_ids"] == [1, 2]
    # El mejor fragmento representa al documento: es el que lo metió en el contexto.
    assert por_doc["d1"]["score"] == 0.95
    assert por_doc["d1"]["title"] == "Uno" and por_doc["d1"]["authors"] == "A"
    assert por_doc["d2"]["chunk_ids"] == [9]


def test_un_fragmento_repetido_no_duplica_su_chunk_id():
    with ex.collecting() as acumulador:
        ex.record_rag_hits("col", [{"doc_id": "d", "chunk_id": 5}, {"doc_id": "d", "chunk_id": 5}])
    assert acumulador.rag_sources[0]["chunk_ids"] == [5]


def test_anotar_fuera_de_un_paso_no_revienta():
    """Observar no puede romper lo observado: el RAG se usa también sin pipeline."""
    assert ex.current() is None
    ex.record_tokens(1, 1)
    ex.record_rag_hits("col", [{"doc_id": "d"}])


def test_los_contextos_no_se_mezclan():
    """Dos ejecuciones a la vez en el mismo proceso son el caso normal."""
    with ex.collecting() as uno:
        ex.record_tokens(10, 0)
        with ex.collecting() as otro:
            ex.record_tokens(1, 0)
        ex.record_tokens(5, 0)
    assert uno.tokens_in == 15
    assert otro.tokens_in == 1


def test_el_texto_largo_se_recorta():
    """La traza explica una ejecución, no es un segundo almacén del artículo."""
    salida = ex.output_text({"draft_text": "x" * (ex.MAX_TEXTO + 500)})
    assert len(salida) < ex.MAX_TEXTO + 200
    assert "recortado" in salida


def test_solo_los_pasos_que_deciden_tienen_decision():
    assert ex.decision_of({"draft_text": "algo"}) is None
    decision = ex.decision_of({"approval_score": 42, "coherent": False, "user_decision": "continue"})
    assert decision == {"score": 42, "coherent": False, "hitl_outcome": "continue"}


def test_el_rationale_sale_del_feedback():
    assert ex.rationale_of({}) is None
    assert "flojo" in ex.rationale_of({"feedback": ["flojo", "corto"]})


def test_los_parametros_salen_de_los_ajustes_del_agente():
    estado = {"agent_settings": {"redactor": {"temperature": 0.3, "target_word_count": 900,
                                              "prompt_template": "no interesa"}}}
    params = ex.params_of("redactor", estado)
    assert params == {"temperature": 0.3, "target_word_count": 900}


# ── De extremo a extremo: el orquestador escribe la traza ───────────────────

@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def sin_registro_de_runs(monkeypatch):
    """`agent_runs` no es lo que se prueba aquí."""
    async def _start(agent_name, article_id, author_id, input_payload):
        return uuid.uuid4()

    async def _end(run_id, output_payload, status, error_message=None):
        return None

    monkeypatch.setattr(orquestador, "log_run_start", _start)
    monkeypatch.setattr(orquestador, "log_run_end", _end)


async def _pasos(article_id=None):
    async with AsyncSessionLocal() as session:
        stmt = select(AgentRunStepModel).order_by(AgentRunStepModel.created_at)
        if article_id is not None:
            stmt = stmt.where(AgentRunStepModel.article_id == article_id)
        return list((await session.execute(stmt)).scalars().all())


@pytest.mark.asyncio
async def test_una_ejecucion_deja_un_paso_por_agente(db, sin_registro_de_runs, monkeypatch):
    async def investigador(state):
        # Simula lo que hace la capacidad de RAG desde dentro del agente.
        ex.record_rag_hits("p_x__rag_docs", [
            {"doc_id": "doc-1", "chunk_id": 11, "score": 0.9, "doc_title": "Un paper",
             "doc_authors": "Autora"},
        ])
        ex.record_tokens(400, 120)
        return {"research_data": "material", "sources": [{"title": "Un paper"}]}

    async def redactor(state):
        ex.record_tokens(900, 700)
        return {"draft_text": "# Borrador\ncontenido"}

    async def revisor(state):
        ex.record_tokens(300, 60)
        return {"approval_score": 91.0, "coherent": True, "feedback": ["bien argumentado"],
                "loop_count": 0, "user_decision": None}

    monkeypatch.setattr(adapter_investigador, "run_investigador", investigador)
    monkeypatch.setattr(adapter_redactor, "run_redactor", redactor)
    monkeypatch.setattr(adapter_revisor, "run_revisor", revisor)

    article_id = uuid.uuid4()
    await orquestador.Orchestrator.run(
        article_id=article_id, author_id=uuid.uuid4(), title="Un título",
        keywords=["uno"], scientific_format="apa",
        flow_sequence=["investigador", "redactor", "revisor"],
    )

    pasos = await _pasos(article_id)
    assert [p.agent_name for p in pasos] == ["investigador", "redactor", "revisor"]

    investiga = pasos[0]
    assert investiga.status == "completed"
    assert investiga.tokens_in == 400 and investiga.tokens_out == 120
    assert investiga.latency_ms > 0
    assert investiga.input_digest and "Un título" in investiga.input_digest
    assert investiga.output_text == "material"
    # AC1: las fuentes que se recuperaron **de verdad**, no las que citó el texto.
    assert investiga.rag_sources == [{
        "doc_id": "doc-1", "collection": "p_x__rag_docs", "title": "Un paper",
        "authors": "Autora", "chunk_ids": [11], "score": 0.9,
    }]

    revisa = pasos[2]
    assert revisa.decision == {"score": 91.0, "coherent": True, "hitl_outcome": None}
    assert "bien argumentado" in revisa.rationale
    # Un paso que no decide no inventa una decisión vacía.
    assert pasos[1].decision is None


@pytest.mark.asyncio
async def test_los_tokens_no_se_mezclan_entre_pasos(db, sin_registro_de_runs, monkeypatch):
    """Sin reiniciar el acumulador, el coste de un agente arrastraría el anterior."""
    async def investigador(state):
        ex.record_tokens(1000, 1000)
        return {"research_data": "x"}

    async def redactor(state):
        ex.record_tokens(7, 3)
        return {"draft_text": "y"}

    monkeypatch.setattr(adapter_investigador, "run_investigador", investigador)
    monkeypatch.setattr(adapter_redactor, "run_redactor", redactor)

    article_id = uuid.uuid4()
    await orquestador.Orchestrator.run(
        article_id=article_id, author_id=uuid.uuid4(), title="T", keywords=[],
        scientific_format="apa", flow_sequence=["investigador", "redactor"],
    )
    pasos = {p.agent_name: p for p in await _pasos(article_id)}
    assert (pasos["redactor"].tokens_in, pasos["redactor"].tokens_out) == (7, 3)


@pytest.mark.asyncio
async def test_un_paso_que_falla_tambien_se_traza(db, sin_registro_de_runs, monkeypatch):
    """AC1 dice «cuando termina **o se cancela**»: el paso que revienta es el que hay que explicar."""
    async def investigador(state):
        ex.record_tokens(50, 0)
        raise RuntimeError("el proveedor no responde")

    monkeypatch.setattr(adapter_investigador, "run_investigador", investigador)

    article_id = uuid.uuid4()
    with pytest.raises(Exception):
        await orquestador.Orchestrator.run(
            article_id=article_id, author_id=uuid.uuid4(), title="T", keywords=[],
            scientific_format="apa", flow_sequence=["investigador"],
        )

    pasos = await _pasos(article_id)
    assert len(pasos) == 1
    assert pasos[0].status == "failed"
    assert "no responde" in pasos[0].error_message
    # Y lo consumido antes de fallar no se pierde: es parte del coste real.
    assert pasos[0].tokens_in == 50


@pytest.mark.asyncio
async def test_el_bucle_de_revision_deja_un_paso_por_vuelta(db, sin_registro_de_runs, monkeypatch):
    """Un paso ≠ un agente: `iteration` distingue las vueltas del mismo agente."""
    vueltas = {"n": 0}

    async def redactor(state):
        return {"draft_text": "borrador"}

    async def revisor(state):
        vueltas["n"] += 1
        if vueltas["n"] == 1:
            return {"approval_score": 10.0, "coherent": False, "feedback": ["flojo"],
                    "loop_count": 1, "user_decision": None}
        return {"approval_score": 95.0, "coherent": True, "feedback": [],
                "loop_count": 1, "user_decision": None}

    monkeypatch.setattr(adapter_redactor, "run_redactor", redactor)
    monkeypatch.setattr(adapter_revisor, "run_revisor", revisor)

    article_id = uuid.uuid4()
    await orquestador.Orchestrator.run(
        article_id=article_id, author_id=uuid.uuid4(), title="T", keywords=[],
        scientific_format="apa", flow_sequence=["redactor", "revisor"],
    )

    pasos = await _pasos(article_id)
    revisiones = [p for p in pasos if p.agent_name == "revisor"]
    assert len(revisiones) == 2
    assert [r.decision["score"] for r in revisiones] == [10.0, 95.0]
    # La segunda vuelta se distingue de la primera.
    assert revisiones[0].iteration != revisiones[1].iteration


@pytest.mark.asyncio
async def test_un_fallo_al_guardar_la_traza_no_tumba_el_pipeline(db, sin_registro_de_runs, monkeypatch, caplog):
    """Observar no puede romper lo observado — pero tampoco callarse."""
    import logging

    async def redactor(state):
        return {"draft_text": "sale igual"}

    def _sesion_rota(*args, **kwargs):
        raise RuntimeError("la base no responde")

    monkeypatch.setattr(adapter_redactor, "run_redactor", redactor)
    # Se rompe la **escritura**, no `log_run_step`: sustituirlo entero quitaría de
    # en medio justo la protección que se quiere probar.
    monkeypatch.setattr(orquestador, "AsyncSessionLocal", _sesion_rota)

    with caplog.at_level(logging.WARNING):
        resultado = await orquestador.Orchestrator.run(
            article_id=uuid.uuid4(), author_id=uuid.uuid4(), title="T", keywords=[],
            scientific_format="apa", flow_sequence=["redactor"],
        )

    assert resultado.get("draft_text") == "sale igual"
    # Y no se calla: una traza que se pierde en silencio da confianza infundada.
    assert any("paso de traza" in registro.message for registro in caplog.records)


# ── Retención: una tabla que acumula rastro tiene que caducar ───────────────

def test_la_traza_esta_en_la_politica_de_retencion():
    """Hay un test de gobernanza que compara la política con el código; este dice
    además que la ventana es **la misma** que la de `agent_runs`: la traza describe
    las mismas ejecuciones y con el mismo detalle."""
    from app.core.config import settings

    assert settings.RETENTION_AGENT_RUN_STEPS_DAYS == settings.RETENTION_AGENT_RUNS_DAYS

    documento = (ROOT_DIR.parent / "docs" / "governance" / "data-retention.md").read_text(
        encoding="utf-8"
    )
    assert "agent_run_steps" in documento
    assert "RETENTION_AGENT_RUN_STEPS_DAYS" in documento


@pytest.mark.asyncio
async def test_la_purga_borra_la_traza_vencida(db):
    from datetime import datetime, timedelta

    from app.platform.retention import purge

    async with AsyncSessionLocal() as session:
        session.add(AgentRunStepModel(
            agent_name="redactor", status="completed",
            created_at=datetime.utcnow() - timedelta(days=400),
        ))
        session.add(AgentRunStepModel(
            agent_name="redactor", status="completed", created_at=datetime.utcnow(),
        ))
        await session.commit()

    async with AsyncSessionLocal() as session:
        resultado = await purge(session, apply=True)

    assert resultado.counts["agent_run_steps"] == 1
    assert len(await _pasos()) == 1


# ── Las dos costuras que hacen que esto funcione sin tocar los agentes ──────

def test_el_dispatcher_del_llm_alimenta_la_traza():
    """`_record_usage` es el único sitio donde se conocen los tokens.

    Los agentes de los tests de arriba llaman a `record_tokens` directamente, así
    que sin este caso la costura real quedaría sin cubrir: se podría borrar la
    llamada de `llm.py` y todo seguiría verde.
    """
    from app.platform import llm

    with ex.collecting() as acumulador:
        llm._record_usage("ollama", "gemma2:2b", 321, 123)
    assert (acumulador.tokens_in, acumulador.tokens_out) == (321, 123)


@pytest.mark.asyncio
async def test_la_capacidad_de_rag_alimenta_la_traza(tmp_path, monkeypatch):
    """Y lo hace también **sin Qdrant**, que es un modo soportado.

    El respaldo local es el camino que se usa en desarrollo y en instalaciones sin
    Qdrant: si solo anotara el camino semántico, esas ejecuciones tendrían una
    traza sin fuentes y nadie se enteraría.
    """
    import json

    from app.platform.capabilities import rag

    coleccion = tmp_path / "p_x__rag_docs"
    coleccion.mkdir()
    (coleccion / "doc-7.json").write_text(json.dumps({
        "doc_id": "doc-7", "agent_name": "investigador", "filename": "fuente.md",
        "doc_title": "Una fuente", "doc_authors": "Autora",
        "chunks": [{"chunk_index": 0, "text": "primer fragmento"},
                   {"chunk_index": 1, "text": "segundo fragmento"}],
    }), encoding="utf-8")

    async def _sin_qdrant(*args, **kwargs):
        return False

    monkeypatch.setattr(rag, "is_qdrant_available", _sin_qdrant)
    monkeypatch.setattr(rag, "_local_collection_dir", lambda _c: coleccion)

    with ex.collecting() as acumulador:
        await rag.semantic_search_results(
            query="algo", qdrant_url="http://nada", collection="p_x__rag_docs",
            agent_name=["investigador"], ollama_base_url="http://nada",
            embedding_model="m", limit=5, score_threshold=0.0,
        )

    assert len(acumulador.rag_sources) == 1
    fuente = acumulador.rag_sources[0]
    assert fuente["doc_id"] == "doc-7"
    assert fuente["chunk_ids"] == [0, 1]
    assert fuente["title"] == "Una fuente"
