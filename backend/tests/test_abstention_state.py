"""SPEC-034 AC13 / T22.12 - la abstencion deja la ejecucion "detenida", no "completada".

El motor ya cortaba el flujo cuando el Investigador se abstenia (T22.5), pero el
orquestador cerraba la ejecucion con `completed` y un `done` indistinguible. Aqui se
comprueba el recorrido entero con la BD real: estado persistido del run y del paso,
evento de cierre, articulo en borrador y ningun agente posterior ejecutado - y que una
ejecucion que si completa no cambia.
"""
import pytest
from sqlalchemy import select

from test_project_isolation import _proyecto, _usuario, db  # noqa: F401  (fixtures y ayudas)
from app.core.database import AsyncSessionLocal
from app.models import AgentRunModel, AgentRunStepModel, ArticleModel, ArticleStatus, UserRole
from app.modules.agents.adapters import (
    formateador as adapter_formateador,
    investigador as adapter_investigador,
    publicador as adapter_publicador,
    redactor as adapter_redactor,
    revisor as adapter_revisor,
)
from app.modules.agents.application import use_cases as orquestador
from app.platform import explainability as ex
from app.platform.summary import _execution_outcome

FLUJO = ["investigador", "redactor", "revisor", "formateador", "publicador"]
MENSAJE = "Faltan fuentes verificadas: 1 de 3."


@pytest.fixture
def pipeline(monkeypatch):
    """Agentes simulados; el registro de runs y pasos es el REAL (es lo que se prueba)."""
    llamados, eventos = [], []
    monkeypatch.setattr(orquestador, "publish_event", lambda aid, ev: eventos.append(ev))

    def agente(nombre, salida):
        async def runner(state):
            llamados.append(nombre)
            return dict(salida)
        return runner

    monkeypatch.setattr(adapter_redactor, "run_redactor",
                        agente("redactor", {"draft_text": "borrador"}))
    monkeypatch.setattr(adapter_revisor, "run_revisor", agente("revisor", {
        "approval_score": 95, "coherent": True, "review_status": "ok", "feedback": [],
        "loop_count": 0, "user_decision": None}))
    monkeypatch.setattr(adapter_formateador, "run_formateador",
                        agente("formateador", {"formatted_text": "fmt"}))
    monkeypatch.setattr(adapter_publicador, "run_publicador",
                        agente("publicador", {"published_url": ""}))
    return llamados, eventos


def _investigador(monkeypatch, llamados, *, abstiene):
    salida = ({
        "research_data": "", "sources": [], "abstained": True,
        "abstention": {"reason": "insufficient_verified_sources", "message": MENSAJE,
                       "verified_sources": 1, "min_sources": 3},
    } if abstiene else {"research_data": "material", "sources": []})

    async def runner(state):
        llamados.append("investigador")
        return dict(salida)

    monkeypatch.setattr(adapter_investigador, "run_investigador", runner)


async def _articulo():
    autora = await _usuario("autora@ejemplo.com", UserRole.REDACTOR)
    proyecto = await _proyecto("P", owner_id=autora.id)
    async with AsyncSessionLocal() as s:
        art = ArticleModel(title="T", body="", author_id=autora.id, project_id=proyecto.id,
                           status=ArticleStatus.DRAFT)
        s.add(art)
        await s.commit()
        await s.refresh(art)
    return autora, art


async def _ejecutar(autora, art):
    await orquestador.Orchestrator.run(
        article_id=art.id, author_id=autora.id, title="T", keywords=[],
        scientific_format="apa", flow_sequence=FLUJO,
    )
    async with AsyncSessionLocal() as s:
        runs = (await s.execute(select(AgentRunModel).where(
            AgentRunModel.article_id == art.id))).scalars().all()
        pasos = (await s.execute(select(AgentRunStepModel).where(
            AgentRunStepModel.article_id == art.id).order_by(
            AgentRunStepModel.step_index))).scalars().all()
        articulo = (await s.execute(select(ArticleModel).where(
            ArticleModel.id == art.id))).scalars().first()
    return runs, pasos, articulo


@pytest.mark.asyncio
async def test_la_abstencion_deja_run_y_paso_en_estado_propio(db, pipeline, monkeypatch):  # noqa: F811
    llamados, eventos = pipeline
    _investigador(monkeypatch, llamados, abstiene=True)
    autora, art = await _articulo()
    runs, pasos, _ = await _ejecutar(autora, art)

    assert ex.STATUS_ABSTAINED == "abstained"
    assert [r.status for r in runs] == ["abstained"]          # ni completed, ni failed, ni cancelled
    assert [(p.agent_name, p.status) for p in pasos] == [("investigador", "abstained")]
    # La abstencion no es un error: no hay mensaje de error ni cuenta como paso fallido.
    assert pasos[0].error_message is None
    assert ex.totals_of(pasos)["failed_steps"] == 0


@pytest.mark.asyncio
async def test_el_cierre_dice_que_fue_abstencion_con_k_sobre_n(db, pipeline, monkeypatch):  # noqa: F811
    llamados, eventos = pipeline
    _investigador(monkeypatch, llamados, abstiene=True)
    autora, art = await _articulo()
    await _ejecutar(autora, art)

    cierre = [e for e in eventos if e["type"] == "done"]
    assert len(cierre) == 1
    assert cierre[0]["outcome"] == "abstained"
    assert cierre[0]["verified_sources"] == 1 and cierre[0]["min_sources"] == 3
    assert cierre[0]["message"] == MENSAJE
    # El aviso `abstained` sigue existiendo y llega antes del cierre.
    tipos = [e["type"] for e in eventos]
    assert tipos.index("abstained") < tipos.index("done")


@pytest.mark.asyncio
async def test_ningun_agente_posterior_corre_y_el_articulo_sigue_en_borrador(db, pipeline, monkeypatch):  # noqa: F811
    llamados, eventos = pipeline
    _investigador(monkeypatch, llamados, abstiene=True)
    autora, art = await _articulo()
    _, pasos, articulo = await _ejecutar(autora, art)

    assert llamados == ["investigador"]
    assert len(pasos) == 1
    assert articulo.status == ArticleStatus.DRAFT
    assert not articulo.body
    iniciados = [e["agent"] for e in eventos if e["type"] == "agent_start"]
    assert iniciados == ["investigador"]


@pytest.mark.asyncio
async def test_la_ejecucion_se_resume_como_detenida_por_abstencion(db, pipeline, monkeypatch):  # noqa: F811
    llamados, _ = pipeline
    _investigador(monkeypatch, llamados, abstiene=True)
    autora, art = await _articulo()
    _, pasos, _ = await _ejecutar(autora, art)

    resultado = _execution_outcome(pasos)
    assert resultado["status"] == "abstained"
    assert resultado["failed"] is False and resultado["failed_steps"] == 0


@pytest.mark.asyncio
async def test_el_paso_abstenido_entra_en_la_cadena_sin_subir_la_version(db, pipeline, monkeypatch):  # noqa: F811
    """`status` ya estaba en el canon: un valor nuevo no cambia el formato ni exige otra version."""
    llamados, _ = pipeline
    _investigador(monkeypatch, llamados, abstiene=True)
    autora, art = await _articulo()
    _, pasos, _ = await _ejecutar(autora, art)

    assert "status" in ex._CAMPOS_CANONICOS
    assert ex.CANON_VERSION == 2
    assert pasos[0].hash_version == ex.CANON_VERSION
    informe = ex.verify_chain(list(pasos))
    assert informe["intact"] is True and informe["verified"] == 1


@pytest.mark.asyncio
async def test_una_ejecucion_que_completa_no_cambia(db, pipeline, monkeypatch):  # noqa: F811
    llamados, eventos = pipeline
    _investigador(monkeypatch, llamados, abstiene=False)
    autora, art = await _articulo()
    runs, pasos, _ = await _ejecutar(autora, art)

    assert llamados == FLUJO
    assert {r.status for r in runs} == {"completed"}
    assert {p.status for p in pasos} == {"completed"}
    cierre = [e for e in eventos if e["type"] == "done"]
    assert cierre == [{"type": "done"}]                         # sin `outcome`: igual que antes
    assert not any(e["type"] == "abstained" for e in eventos)
    assert _execution_outcome(pasos)["status"] == "completed"
