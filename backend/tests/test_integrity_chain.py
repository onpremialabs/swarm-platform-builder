"""Cadena de integridad de la traza (SPEC-029 / T17.2, T17.3).

AC4: cada paso lleva `sha256(canónico || hash_anterior)`, anclado en el primero.
AC5: la verificación detecta un paso alterado, borrado o insertado, y dice cuál.
AC7: una reejecución o una reanudación no producen falso positivo.
"""
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

TEST_DB_PATH = (ROOT_DIR / "tests" / "test_integrity_chain.db").resolve()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    AgentRunStepModel, ArticleModel, ProjectModel, UserModel, UserRole,
)
from app.platform import explainability as ex  # noqa: E402


class _Paso:
    """Una fila de traza, con solo lo que entra en el hash."""

    def __init__(self, **campos):
        base = {
            "article_id": "a-1", "project_id": "p-1", "agent_name": "redactor",
            "step_index": 0, "iteration": 0, "status": "completed",
            "error_message": None, "model": "mistral:7b", "params": {"temperature": 0.7},
            "input_digest": "resumen", "output_text": "texto", "rag_sources": [],
            "tokens_in": 10, "tokens_out": 20, "latency_ms": 1500.0,
            "decision": None, "rationale": None,
            "content_hash": None, "prev_hash": None, "hash_version": ex.CANON_VERSION,
        }
        base.update(campos)
        for k, v in base.items():
            setattr(self, k, v)


def _encadenar(pasos):
    """Sella una ejecución como lo hace `log_run_step`."""
    anterior = None
    for paso in pasos:
        anterior = None if paso.step_index == 0 else anterior
        paso.prev_hash = anterior
        paso.content_hash = ex.compute_hash(paso, anterior)
        anterior = paso.content_hash
    return pasos


# ── AC4: la serialización canónica ──────────────────────────────────────────

def test_el_canonico_no_depende_del_orden_de_las_claves():
    """Dos dicts con las mismas claves en distinto orden deben dar el mismo hash.

    Si dependiera del orden, la verificación fallaría según de dónde viniera la
    fila —del dict de escritura o del ORM— y la cadena sería inútil.
    """
    uno = {"agent_name": "redactor", "step_index": 1, "tokens_in": 5}
    otro = {"tokens_in": 5, "step_index": 1, "agent_name": "redactor"}
    assert ex.canonical_form(uno) == ex.canonical_form(otro)


def test_el_canonico_es_igual_desde_dict_y_desde_fila():
    """Escribir y verificar usan el mismo código sobre formas distintas del paso."""
    campos = {
        "article_id": "a-1", "project_id": "p-1", "agent_name": "revisor",
        "step_index": 2, "iteration": 1, "status": "completed",
        "model": "m", "params": {"b": 2, "a": 1}, "input_digest": "d",
        "output_text": "o", "rag_sources": [{"doc_id": "x"}],
        "tokens_in": 1, "tokens_out": 2, "latency_ms": 10.0,
        "decision": {"score": 90}, "rationale": "r", "error_message": None,
    }
    assert ex.canonical_form(campos) == ex.canonical_form(_Paso(**campos))


def test_el_primer_paso_ancla_en_un_valor_conocido():
    """AC4: sin ancla, insertar un paso al principio no rompería nada."""
    paso = _Paso(step_index=0)
    con_ancla = ex.compute_hash(paso, None)
    explicito = ex.compute_hash(paso, ex.ANCLA_GENESIS)
    assert con_ancla == explicito, "None y el ancla deben tratarse igual"


def test_cambiar_un_campo_cambia_el_hash():
    base = _Paso()
    assert ex.compute_hash(base, None) != ex.compute_hash(_Paso(tokens_out=21), None)
    assert ex.compute_hash(base, None) != ex.compute_hash(_Paso(output_text="otro"), None)


def test_el_mismo_paso_en_distinta_posicion_da_distinto_hash():
    """El hash anterior entra dentro del digest: un paso no se puede recolocar."""
    paso = _Paso(step_index=1)
    assert ex.compute_hash(paso, "aa" * 32) != ex.compute_hash(paso, "bb" * 32)


# ── AC5: la verificación localiza el problema ───────────────────────────────

def test_una_cadena_intacta_se_verifica():
    pasos = _encadenar([_Paso(step_index=i, agent_name=f"ag{i}") for i in range(4)])
    informe = ex.verify_chain(pasos)
    assert informe["intact"] is True
    assert informe["issues"] == []
    assert informe["verified"] == 4
    assert informe["unchained"] == 0


def test_alterar_una_fila_se_detecta_y_se_localiza():
    """AC5: el informe dice **cuál** paso y en qué posición."""
    pasos = _encadenar([_Paso(step_index=i, agent_name=f"ag{i}") for i in range(4)])

    pasos[2].output_text = "alguien edito esto en la base"

    informe = ex.verify_chain(pasos)
    assert informe["intact"] is False
    alterados = [p for p in informe["issues"] if p["problem"] == "contenido_alterado"]
    assert len(alterados) == 1
    assert alterados[0]["position"] == 2
    assert alterados[0]["agent_name"] == "ag2"


def test_borrar_una_del_medio_se_detecta_y_se_localiza():
    """AC5: un borrado rompe el enlace del siguiente, y se dice dónde."""
    pasos = _encadenar([_Paso(step_index=i, agent_name=f"ag{i}") for i in range(4)])

    del pasos[1]

    informe = ex.verify_chain(pasos)
    assert informe["intact"] is False
    rotos = [p for p in informe["issues"] if p["problem"] == "enlace_roto"]
    assert rotos, "un borrado en medio debe romper el enlace"
    # Tras borrar el índice 1, el que estaba en 2 ocupa la posición 1.
    assert rotos[0]["position"] == 1
    assert rotos[0]["agent_name"] == "ag2"


def test_insertar_una_fila_se_detecta():
    pasos = _encadenar([_Paso(step_index=i, agent_name=f"ag{i}") for i in range(3)])
    intruso = _Paso(step_index=9, agent_name="intruso")
    intruso.content_hash = ex.compute_hash(intruso, pasos[0].content_hash)
    intruso.prev_hash = pasos[0].content_hash
    pasos.insert(1, intruso)

    informe = ex.verify_chain(pasos)
    assert informe["intact"] is False
    assert informe["issues"], "una inserción debe romper la cadena"


def test_una_ejecucion_entera_sin_cadena_no_es_una_cadena_rota():
    """El caso de los datos que ya existían: ni un solo paso lleva hash.

    Colapsarlo en `intact: False` lo pintaba como «cadena rota» en la interfaz.
    No hay nada roto: no hay nada que comprobar, y decir lo contrario entrena a
    ignorar la alarma cuando alguna vez sea de verdad.
    """
    pasos = [_Paso(step_index=i) for i in range(5)]
    for p in pasos:
        p.content_hash = None
        p.hash_version = None

    informe = ex.verify_chain(pasos)
    assert informe["status"] == "sin_cadena"
    assert informe["intact"] is False, "tampoco se puede afirmar que esté íntegra"
    assert informe["issues"] == []
    assert informe["unchained"] == 5
    assert informe["verified"] == 0


def test_los_tres_estados_se_distinguen():
    intacta = _encadenar([_Paso(step_index=i) for i in range(3)])
    assert ex.verify_chain(intacta)["status"] == "intacta"

    rota = _encadenar([_Paso(step_index=i) for i in range(3)])
    rota[1].output_text = "editado"
    assert ex.verify_chain(rota)["status"] == "rota"

    sin_cadena = [_Paso(step_index=0)]
    sin_cadena[0].content_hash = None
    assert ex.verify_chain(sin_cadena)["status"] == "sin_cadena"


def test_un_paso_sin_hash_no_se_cuenta_como_manipulado():
    """Filas anteriores a T17.2: ausencia de prueba no es prueba de manipulación."""
    pasos = _encadenar([_Paso(step_index=i) for i in range(2)])
    viejo = _Paso(step_index=2)
    viejo.content_hash = None
    viejo.hash_version = None
    pasos.append(viejo)

    informe = ex.verify_chain(pasos)
    assert informe["unchained"] == 1
    assert informe["verified"] == 2
    assert not [p for p in informe["issues"] if p["problem"] == "contenido_alterado"]


# ── AC7: reejecución y reanudación no dan falso positivo ────────────────────

def test_una_reejecucion_no_da_falso_positivo():
    """Dos pasadas del mismo artículo son dos cadenas, no una rota.

    `group_executions` las separa porque `step_index` vuelve a 0; verificar cada
    grupo por separado es lo que evita la falsa alarma.
    """
    primera = _encadenar([_Paso(step_index=i, agent_name=f"ag{i}") for i in range(3)])
    segunda = _encadenar([_Paso(step_index=i, agent_name=f"ag{i}") for i in range(2)])

    todos = primera + segunda
    grupos = ex.group_executions(todos)
    assert len(grupos) == 2, "la reejecución debe abrir una ejecución nueva"

    for grupo in grupos:
        assert ex.verify_chain(grupo)["intact"] is True


def test_una_reanudacion_continua_la_misma_cadena():
    """Un `resume` no reinicia `step_index`, así que sigue la numeración."""
    pasos = _encadenar([_Paso(step_index=i, agent_name=f"ag{i}") for i in range(5)])
    grupos = ex.group_executions(pasos)
    assert len(grupos) == 1, "una reanudación no abre ejecución nueva"
    assert ex.verify_chain(grupos[0])["intact"] is True


# ── Integración: la cadena se sella de verdad al escribir el paso ───────────

@pytest_asyncio.fixture
async def esquema():
    """Esquema limpio por test, sin borrar el fichero.

    Mismo motivo que en `test_dashboard_summary`: `engine` es un singleton de
    módulo y al correr la suite entera lo fija el primer test que lo importe,
    que no tiene por qué ser este.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def ejecucion(esquema):
    """Un artículo con tres pasos escritos por el camino real (`log_run_step`)."""
    from app.modules.agents.application.use_cases import log_run_step

    async with AsyncSessionLocal() as s:
        admin = UserModel(
            email="admin@cadena", hashed_password=hash_password("pw"),
            full_name="Admin", role=UserRole.ADMIN, is_active=True,
        )
        s.add(admin)
        await s.flush()
        proyecto = ProjectModel(name="Proyecto cadena", owner_id=admin.id)
        s.add(proyecto)
        await s.flush()
        articulo = ArticleModel(title="Art", author_id=admin.id, project_id=proyecto.id)
        s.add(articulo)
        await s.commit()
        datos = {"admin_id": admin.id, "project_id": proyecto.id,
                 "article_id": articulo.id, "email": admin.email}

    for indice, agente in enumerate(["investigador", "redactor", "revisor"]):
        await log_run_step(
            article_id=datos["article_id"], project_id=datos["project_id"],
            agent_name=agente, step_index=indice, iteration=0,
            status="completed", model="m", params={},
            input_digest=f"entrada {indice}", output_text=f"salida {indice}",
            rag_sources=[], tokens_in=10, tokens_out=20, latency_ms=100.0,
        )
    return datos


async def _pasos(article_id):
    async with AsyncSessionLocal() as s:
        from sqlalchemy import select
        return list((await s.execute(
            select(AgentRunStepModel)
            .where(AgentRunStepModel.article_id == article_id)
            .order_by(AgentRunStepModel.created_at, AgentRunStepModel.step_index)
        )).scalars().all())


@pytest.mark.asyncio
async def test_log_run_step_sella_la_cadena(ejecucion):
    """AC4: el hash se calcula al cerrar el paso, no en un trabajo aparte."""
    pasos = await _pasos(ejecucion["article_id"])
    assert len(pasos) == 3

    assert all(p.content_hash for p in pasos), "algún paso se guardó sin hash"
    assert all(p.hash_version == ex.CANON_VERSION for p in pasos)

    # El primero ancla; los demás enlazan con el anterior.
    assert pasos[0].prev_hash is None
    assert pasos[1].prev_hash == pasos[0].content_hash
    assert pasos[2].prev_hash == pasos[1].content_hash

    assert ex.verify_chain(pasos)["intact"] is True


@pytest.mark.asyncio
async def test_el_endpoint_verifica_y_declara_sus_limites(ejecucion):
    """AC5 + AC6: el informe dice si está íntegra **y** qué no garantiza."""
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/api/v1/auth/login",
                          json={"email": ejecucion["email"], "password": "pw"})
        token = r.json()["access_token"]
        r = await ac.get(f"/api/v1/agents/{ejecucion['article_id']}/integrity",
                         headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        cuerpo = r.json()

    assert cuerpo["available"] is True
    assert cuerpo["intact"] is True
    assert len(cuerpo["executions"]) == 1
    assert cuerpo["executions"][0]["verified"] == 3

    # AC6: los límites viajan en la respuesta para que la interfaz no pueda
    # enseñar el sello sin enseñarlos.
    assert "reescribir la base entera" in cuerpo["scope"]["does_not_guarantee"]
    assert cuerpo["scope"]["guarantees"]


@pytest.mark.asyncio
async def test_alterar_la_fila_en_la_base_se_detecta_por_el_endpoint(ejecucion):
    """AC5 sobre datos reales: editar la tabla rompe la verificación."""
    from app.main import app
    from sqlalchemy import select

    async with AsyncSessionLocal() as s:
        paso = (await s.execute(
            select(AgentRunStepModel)
            .where(AgentRunStepModel.article_id == ejecucion["article_id"])
            .where(AgentRunStepModel.step_index == 1)
        )).scalars().first()
        paso.output_text = "alguien edito esto directamente en la base"
        s.add(paso)
        await s.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/api/v1/auth/login",
                          json={"email": ejecucion["email"], "password": "pw"})
        token = r.json()["access_token"]
        r = await ac.get(f"/api/v1/agents/{ejecucion['article_id']}/integrity",
                         headers={"Authorization": f"Bearer {token}"})
        cuerpo = r.json()

    assert cuerpo["intact"] is False
    problemas = cuerpo["executions"][0]["issues"]
    assert any(p["problem"] == "contenido_alterado" and p["agent_name"] == "redactor"
               for p in problemas), problemas


@pytest.mark.asyncio
async def test_la_exportacion_jsonl_lleva_cabecera_hashes_y_respeta_la_retencion(ejecucion):
    """AC3: esquema versionado, hashes incluidos, y nada que la traza no guarde."""
    from app.main import app
    import json as _json

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/api/v1/auth/login",
                          json={"email": ejecucion["email"], "password": "pw"})
        token = r.json()["access_token"]
        r = await ac.get(f"/api/v1/agents/{ejecucion['article_id']}/export.jsonl",
                         headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        lineas = [l for l in r.text.splitlines() if l.strip()]

    cabecera = _json.loads(lineas[0])
    assert cabecera["type"] == "header"
    assert cabecera["schema_version"] >= 1
    assert cabecera["canon_version"] == ex.CANON_VERSION
    assert cabecera["steps"] == 3

    filas = [_json.loads(l) for l in lineas[1:]]
    assert len(filas) == 3
    # Los hashes van dentro: es lo que hace el export verificable fuera.
    assert all(f["content_hash"] for f in filas)
    # Y no se cuela nada que la traza no guarde: el resumen sigue siendo resumen.
    assert filas[0]["input_digest"] == "entrada 0"
    assert "prompt" not in filas[0]
