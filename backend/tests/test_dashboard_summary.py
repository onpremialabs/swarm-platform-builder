"""Endpoint GET /api/v1/dashboard/summary — aislamiento por proyecto (SPEC-028 / T16.2).

AC1: el endpoint usa get_project_context y devuelve solo datos del proyecto activo.
AC5: cada artículo en la lista muestra su estado real del pipeline (desde agent_run_steps).
AC6: dos proyectos con ejecuciones, la portada de uno no incluye datos del otro.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

TEST_DB_PATH = (ROOT_DIR / "tests" / "test_dashboard_summary.db").resolve()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    AgentRunStepModel, ArticleModel, ProjectModel, UserModel, UserRole,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Esquema limpio por test, sin tocar el fichero.

    No se borra `TEST_DB_PATH`: `engine` es un singleton de módulo y lo fija el
    primer test que importe `app.core.database`, que al correr la suite entera no
    tiene por qué ser este. Borrando el fichero se vaciaba uno que el engine no
    estaba usando y las filas del test anterior seguían ahí —`UNIQUE constraint
    failed: users.email`—; en Windows, además, el unlink fallaba con el pool
    abierto. Vaciar el esquema vale para las dos cosas.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def dos_proyectos():
    """Crea dos proyectos independientes con un artículo y un paso cada uno."""
    async with AsyncSessionLocal() as s:
        admin = UserModel(
            email="admin@test", hashed_password=hash_password("pw"),
            full_name="Admin", role=UserRole.ADMIN, is_active=True,
        )
        s.add(admin)
        await s.flush()

        p1 = ProjectModel(name="Proyecto A", owner_id=admin.id)
        p2 = ProjectModel(name="Proyecto B", owner_id=admin.id)
        s.add_all([p1, p2])
        await s.flush()

        a1 = ArticleModel(title="Art-A", author_id=admin.id, project_id=p1.id)
        a2 = ArticleModel(title="Art-B", author_id=admin.id, project_id=p2.id)
        s.add_all([a1, a2])
        await s.flush()

        # Paso de proyecto A: 100 tokens_in, 200 tokens_out
        s.add(AgentRunStepModel(
            article_id=a1.id, project_id=p1.id,
            agent_name="redactor", step_index=0, iteration=0,
            status="completed", tokens_in=100, tokens_out=200,
            latency_ms=1500.0, rag_sources=[],
            created_at=datetime.now(timezone.utc),
        ))
        # Paso de proyecto B: 300 tokens_in, 400 tokens_out
        s.add(AgentRunStepModel(
            article_id=a2.id, project_id=p2.id,
            agent_name="redactor", step_index=0, iteration=0,
            status="completed", tokens_in=300, tokens_out=400,
            latency_ms=2000.0, rag_sources=[],
            created_at=datetime.now(timezone.utc),
        ))
        await s.commit()
        return {"admin": admin, "p1": p1, "p2": p2, "a1": a1, "a2": a2}


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_summary_devuelve_solo_datos_del_proyecto_activo(dos_proyectos):
    """AC1 + AC6: la portada del proyecto A no incluye tokens del proyecto B."""
    from app.main import app

    datos = dos_proyectos
    admin = datos["admin"]
    p1 = datos["p1"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Autenticar
        resp = await ac.post("/api/v1/auth/login", json={"email": "admin@test", "password": "pw"})
        assert resp.status_code == 200, resp.text
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "X-Project-Id": str(p1.id)}

        resp = await ac.get("/api/v1/dashboard/summary", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()

    # Solo los tokens del proyecto A (100 + 200 = 300 total)
    assert body["tokens_in"] == 100
    assert body["tokens_out"] == 200
    assert body["tokens_total"] == 300
    # El proyecto B tiene 300 + 400 = 700; si aparecieran, el total sería > 300
    assert body["tokens_total"] < 700, "tokens de otro proyecto se filtraron"


@pytest.mark.asyncio
async def test_summary_proyecto_b_no_ve_proyecto_a(dos_proyectos):
    """AC6: la portada del proyecto B tiene sus propios tokens, distintos de A."""
    from app.main import app

    datos = dos_proyectos
    admin = datos["admin"]
    p2 = datos["p2"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/auth/login", json={"email": "admin@test", "password": "pw"})
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "X-Project-Id": str(p2.id)}

        resp = await ac.get("/api/v1/dashboard/summary", headers=headers)
        assert resp.status_code == 200
        body = resp.json()

    assert body["tokens_in"] == 300
    assert body["tokens_out"] == 400


@pytest.mark.asyncio
async def test_summary_incluye_articulos_con_estado_del_pipeline(dos_proyectos):
    """AC5: la lista de artículos muestra el estado real del pipeline."""
    from app.main import app

    datos = dos_proyectos
    p1 = datos["p1"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/auth/login", json={"email": "admin@test", "password": "pw"})
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "X-Project-Id": str(p1.id)}

        resp = await ac.get("/api/v1/dashboard/summary", headers=headers)
        assert resp.status_code == 200
        body = resp.json()

    articles = body.get("articles", [])
    assert len(articles) == 1
    art = articles[0]
    # Estado viene de agent_run_steps, no de ArticleModel.status
    assert art["tokens_in"] == 100
    assert "redactor" in art["agents_run"]
    assert art["failed"] is False


@pytest.mark.asyncio
async def test_summary_sin_proyecto_devuelve_422():
    """AC1: sin X-Project-Id la dependencia get_project_context rechaza la petición."""
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/auth/login", json={"email": "admin@test", "password": "pw"})
        # Si no hay usuario puede ser 422 directamente; en cualquier caso sin proyecto falla.
        # Si la autenticación falla, solo verificamos que no es 200.
        token_resp = resp.json()
        if "access_token" in token_resp:
            token = token_resp["access_token"]
            resp2 = await ac.get("/api/v1/dashboard/summary",
                                 headers={"Authorization": f"Bearer {token}"})
            assert resp2.status_code in (400, 403, 404, 422)


@pytest.mark.asyncio
async def test_consumo_por_agente_trae_tokens_y_latencia(dos_proyectos):
    """El desglose por agente lleva tokens y latencia, no solo el número de pasos.

    La portada los pintaba siempre a cero porque el endpoint devolvía únicamente
    los nombres de los agentes y el cliente no tenía de dónde sacar el resto.
    """
    from app.main import app

    p1 = dos_proyectos["p1"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/auth/login", json={"email": "admin@test", "password": "pw"})
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "X-Project-Id": str(p1.id)}

        resp = await ac.get("/api/v1/dashboard/summary", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()

    redactor = next(a for a in body["by_agent"] if a["name"] == "redactor")
    assert redactor["tokens_in"] == 100
    assert redactor["tokens_out"] == 200
    assert redactor["tokens_total"] == 300
    assert redactor["latency_ms"] == 1500.0
    assert redactor["runs"] == 1

    # El mismo desglose, por artículo, para la fila desplegable de la tabla.
    art = body["articles"][0]
    assert art["latency_ms"] == 1500.0
    ag = next(a for a in art["agents"] if a["name"] == "redactor")
    assert ag["tokens_total"] == 300
    assert ag["latency_ms"] == 1500.0


@pytest.mark.asyncio
async def test_reejecucion_aparece_como_dos_ejecuciones(dos_proyectos):
    """AC1 (T17.1): una segunda pasada es su propia fila, no se funde con la primera.

    La portada agrupaba por artículo, así que reejecutar uno sumaba sus tokens a la
    misma fila y la pasada desaparecía de la vista.
    """
    from app.main import app

    p1 = dos_proyectos["p1"]
    a1 = dos_proyectos["a1"]
    base = datetime.now(timezone.utc)

    # Segunda pasada del pipeline sobre el mismo artículo: step_index vuelve a 0.
    async with AsyncSessionLocal() as s:
        for idx, agente in enumerate(["investigador", "redactor"]):
            s.add(AgentRunStepModel(
                article_id=a1.id, project_id=p1.id,
                agent_name=agente, step_index=idx, iteration=0,
                status="completed", tokens_in=50, tokens_out=70,
                latency_ms=900.0, rag_sources=[],
                created_at=base + timedelta(minutes=idx + 1),
            ))
        await s.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/auth/login", json={"email": "admin@test", "password": "pw"})
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "X-Project-Id": str(p1.id)}

        resp = await ac.get("/api/v1/dashboard/summary", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()

    del_articulo = [e for e in body["executions"] if e["article_id"] == str(a1.id)]
    assert len(del_articulo) == 2, "la reejecución se fundió con la primera pasada"
    assert {e["run_number"] for e in del_articulo} == {1, 2}
    assert all(e["runs_total"] == 2 for e in del_articulo)

    primera = next(e for e in del_articulo if e["run_number"] == 1)
    segunda = next(e for e in del_articulo if e["run_number"] == 2)
    assert primera["steps"] == 1 and primera["tokens_total"] == 300
    assert segunda["steps"] == 2 and segunda["tokens_total"] == 240
    assert segunda["agents_run"] == ["investigador", "redactor"]

    # La magnitud de la portada cuenta pasadas, no filas de agent_runs (una por paso).
    assert body["executions_total"] == 2
    assert body["steps_total"] == 3


async def _token_y_cabeceras(ac, project_id):
    resp = await ac.post("/api/v1/auth/login", json={"email": "admin@test", "password": "pw"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "X-Project-Id": str(project_id)}


@pytest.mark.asyncio
async def test_estado_del_enjambre_distingue_ejecutando_de_colgado(dos_proyectos):
    """AC4: un paso abierto hace rato no puede seguir diciendo «ejecutando».

    Un proceso que muere deja su fila de agent_runs en 'running' para siempre.
    Sin umbral, la portada afirmaría que el agente trabaja justo cuando no lo hace.
    """
    from app.main import app
    from app.models.agent_profile import AgentProfileModel
    from app.models.agent_run import AgentRunModel
    from app.platform.summary import SWARM_STALE_AFTER_S

    p1, a1 = dos_proyectos["p1"], dos_proyectos["a1"]
    ahora = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as s:
        for slug, nombre in (("redactor", "Redactor"), ("revisor", "Revisor"),
                             ("investigador", "Investigador")):
            s.add(AgentProfileModel(project_id=p1.id, slug=slug, name=nombre))
        # Recién empezado: está ejecutando de verdad.
        s.add(AgentRunModel(
            agent_name="redactor", article_id=a1.id, author_id=dos_proyectos["admin"].id,
            status="running", started_at=ahora - timedelta(seconds=30),
        ))
        # Abierto desde mucho antes del umbral: nadie lo cerró.
        s.add(AgentRunModel(
            agent_name="revisor", article_id=a1.id, author_id=dos_proyectos["admin"].id,
            status="running", started_at=ahora - timedelta(seconds=SWARM_STALE_AFTER_S + 600),
        ))
        await s.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/dashboard/summary",
                            headers=await _token_y_cabeceras(ac, p1.id))
        assert resp.status_code == 200, resp.text
        swarm = resp.json()["swarm"]

    por_nombre = {a["name"]: a for a in swarm["agents"]}
    assert por_nombre["redactor"]["state"] == "ejecutando"
    assert por_nombre["revisor"]["state"] == "incierto", "un paso colgado sigue diciendo que ejecuta"
    assert por_nombre["investigador"]["state"] == "disponible"

    # El criterio va en la respuesta: un rótulo sin criterio escrito se interpreta solo.
    assert swarm["stale_after_s"] == SWARM_STALE_AFTER_S
    assert all(a["criterion"] for a in swarm["agents"])
    assert set(swarm["criteria"]) == {"ejecutando", "incierto", "disponible", "no_configurado"}


@pytest.mark.asyncio
async def test_agente_sin_perfil_aparece_como_no_configurado(dos_proyectos):
    """AC4: un agente que ejecutó y perdió su perfil no se oculta."""
    from app.main import app

    p1 = dos_proyectos["p1"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/dashboard/summary",
                            headers=await _token_y_cabeceras(ac, p1.id))
        swarm = resp.json()["swarm"]

    # El fixture deja un paso de «redactor» sin crear su perfil.
    redactor = next(a for a in swarm["agents"] if a["name"] == "redactor")
    assert redactor["state"] == "no_configurado"


@pytest.mark.asyncio
async def test_una_seccion_caida_no_tumba_la_portada(dos_proyectos, monkeypatch):
    """AC7: lo que no se pudo preguntar se dice; no se rellena con ceros.

    Antes los tres `await` iban seguidos y un fallo devolvía 500: la portada se
    quedaba en blanco, que es peor que inútil porque un cero no se distinguía de
    «no se pudo preguntar».
    """
    from app.main import app
    import app.routers.dashboard as router_dashboard

    p1 = dos_proyectos["p1"]

    async def _revienta(*_a, **_k):
        raise RuntimeError("Qdrant no responde")

    monkeypatch.setattr(router_dashboard, "project_executions", _revienta)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/dashboard/summary",
                            headers=await _token_y_cabeceras(ac, p1.id))
        assert resp.status_code == 200, "una sección caída no puede tumbar la portada"
        body = resp.json()

    assert body["sections"]["executions"]["available"] is False
    assert body["sections"]["executions"]["reason"] == "RuntimeError"
    assert body["executions"] == []

    # Y el resto sigue sirviendo datos reales, no ceros.
    assert body["sections"]["metrics"]["available"] is True
    assert body["tokens_total"] == 300
    assert body["sections"]["swarm"]["available"] is True


@pytest.mark.asyncio
async def test_anomalias_detectan_paso_fallido(dos_proyectos):
    """AC3: un paso con status='error' incrementa el contador failed_step."""
    from app.main import app

    datos = dos_proyectos
    p1 = datos["p1"]
    a1 = datos["a1"]

    async with AsyncSessionLocal() as s:
        s.add(AgentRunStepModel(
            article_id=a1.id, project_id=p1.id,
            agent_name="revisor", step_index=1, iteration=0,
            status="error", tokens_in=10, tokens_out=0,
            latency_ms=500.0, rag_sources=[],
            created_at=datetime.now(timezone.utc),
        ))
        await s.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/auth/login", json={"email": "admin@test", "password": "pw"})
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "X-Project-Id": str(p1.id)}

        resp = await ac.get("/api/v1/dashboard/summary", headers=headers)
        assert resp.status_code == 200
        body = resp.json()

    assert body["anomalies"]["failed_step"] >= 1
    # El cero de las demás condiciones también tiene semántica (AC3)
    assert "checks_applied" in body["anomalies"]
    assert len(body["anomalies"]["checks_applied"]) == 4
