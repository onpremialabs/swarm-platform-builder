"""SPEC-034 / T22.7 — registro de búsqueda reproducible, traza y exportación (AC6). Sin red real.

Lo que se vigila: que **toda** búsqueda deja registro (completa, parcial y fallida), que
con el registro se puede reconstruir qué se consultó, que no se guarda nada que no sea la
cadena y metadatos de resultados (ni texto del manuscrito, ni claves, ni el correo de
contacto), que la búsqueda queda anotada en el paso de la traza sin tocar al agente, que
la lectura y la exportación la incluyen con un formato estable y que el aislamiento por
proyecto se mantiene.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

TEST_DB_PATH = (ROOT_DIR / "tests" / "test_literature_search_record.db").resolve()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    AgentRunStepModel, ArticleModel, ProjectModel, SearchLogModel, UserModel, UserRole,
)
from app.platform import explainability as ex, library  # noqa: E402
from app.platform.capabilities.literature import (  # noqa: E402
    LiteratureConfig, run_literature_search,
)
from app.platform.capabilities.literature.run import sanitize_filters  # noqa: E402
from app.platform.publication_gate import reference_resolver as rr  # noqa: E402
from app.routers.agents import EXPORT_SCHEMA, EXPORT_SCHEMA_VERSION  # noqa: E402

CORREO = "contacto-secreto@ejemplo.org"
CLAVE = "clave-s2-muy-secreta"
CFG = LiteratureConfig(retries=1, backoff_s=0.0, max_backoff_s=0.0, max_results=5,
                       contact_email=CORREO, semantic_scholar_key=CLAVE)


# ── Simulación de las bases (descubrimiento) y del resolver (verificación) ──

class Resp:
    def __init__(self, status=200, data=None):
        self.status_code, self._data, self.text, self.headers = status, data, "", {}

    def json(self):
        return self._data


OPENALEX = {"results": [
    {"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1038/nature14539",
     "title": "Deep learning", "publication_year": 2015, "publication_date": "2015-05-27",
     "authorships": [{"author": {"display_name": "Yann LeCun"}}],
     "primary_location": {"source": {"display_name": "Nature"}}},
    {"id": "https://openalex.org/W2", "doi": "https://doi.org/10.9999/inventado",
     "title": "Un artículo que no existe", "publication_year": 2020,
     "authorships": [{"author": {"display_name": "Nadie"}}], "primary_location": None},
]}
CROSSREF = {"status": "ok", "message": {"items": []}}


def descubrimiento(crossref=None, openalex=None):
    """`fetch` del descubrimiento: respuesta por host; una excepción simula una base caída."""
    por_host = {"api.openalex.org": openalex or Resp(200, OPENALEX),
                "api.crossref.org": crossref or Resp(200, CROSSREF)}

    async def fetch(url, **kw):
        r = por_host[httpx.URL(url).host]
        if isinstance(r, Exception):
            raise r
        return r
    return fetch


async def _nosleep(_):
    pass


class Registro:
    """Resolver de la verificación: Crossref por DOI. Solo conoce `nature14539`."""

    def __init__(self, caido=False):
        self.caido = caido

    async def __call__(self, url, *, params=None, headers=None, timeout=10.0):
        if self.caido:
            raise ConnectionError("sin red")
        if url == rr.CROSSREF + "/10.1038/nature14539":
            return Resp(200, {"message": {
                "DOI": "10.1038/nature14539", "title": ["Deep learning"], "type": "journal-article",
                "author": [{"family": "LeCun"}], "issued": {"date-parts": [[2015]]},
                "container-title": ["Nature"]}})
        if url == rr.CROSSREF:
            return Resp(200, {"message": {"items": []}})
        if url == rr.OPENALEX:
            return Resp(200, {"results": []})
        return Resp(404)


def verif(caido=False):
    return {"fetch": Registro(caido), "sleep": _nosleep,
            "resolver": rr.ResolverConfig(retries=1)}


# ── Base de datos y mundo ───────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def world(db):
    async with AsyncSessionLocal() as s:
        user = UserModel(email="autora@ejemplo.com", hashed_password=hash_password("Contrasena-1234"),
                         full_name="Autora", role=UserRole.REDACTOR, is_active=True)
        otra = UserModel(email="otra@ejemplo.com", hashed_password=hash_password("Contrasena-1234"),
                         full_name="Otra", role=UserRole.REDACTOR, is_active=True)
        s.add_all([user, otra])
        await s.commit()
        p1 = ProjectModel(name="P1", owner_id=user.id)
        p2 = ProjectModel(name="P2", owner_id=otra.id)
        s.add_all([p1, p2])
        await s.commit()
        a1 = ArticleModel(title="Art 1", body="TEXTO-DEL-MANUSCRITO-NO-DEBE-GUARDARSE",
                          author_id=user.id, project_id=p1.id)
        a2 = ArticleModel(title="Art 2", body="b", author_id=otra.id, project_id=p2.id)
        s.add_all([a1, a2])
        await s.commit()
        return {"user": user.id, "otra": otra.id, "p1": p1.id, "p2": p2.id,
                "a1": a1.id, "a2": a2.id}


async def buscar(world, **kw):
    kw.setdefault("config", CFG)
    kw.setdefault("sleep", _nosleep)
    kw.setdefault("verification", verif())
    kw.setdefault("article_id", world["a1"])
    kw.setdefault("user_id", world["user"])
    kw.setdefault("fetch", descubrimiento())
    project_id = kw.pop("project_id", world["p1"])
    query = kw.pop("query", "deep learning")
    async with AsyncSessionLocal() as s:
        return await run_literature_search(s, project_id, query, **kw)


async def logs():
    async with AsyncSessionLocal() as s:
        return list(await s.scalars(select(SearchLogModel).order_by(SearchLogModel.searched_at)))


# ── Registro: completa, parcial, fallida ────────────────────────────────────

@pytest.mark.asyncio
async def test_busqueda_completa_deja_un_registro_reproducible(world):
    antes = datetime.utcnow()
    salida = await buscar(world, filters={"year_from": 2010, "lang": "en"})
    (log,) = await logs()

    assert salida.status == "completed" == log.status
    assert log.query == "deep learning"
    assert log.sources == ["openalex", "crossref"]
    # Los filtros y el tope con el que se consultó, para poder repetirla igual.
    assert log.filters == {"year_from": 2010, "lang": "en", "limit": 5}
    assert (log.result_count, log.verified_count) == (2, 1)
    # Cada descartado con su motivo.
    assert log.discarded == {"unresolved": 1}
    assert log.per_source["openalex"] == {
        "status": "ok", "returned": 2, "verified": 1, "dropped": 0, "attempts": 1, "error_kind": None}
    assert log.per_source["crossref"]["status"] == "ok" and log.per_source["crossref"]["returned"] == 0
    assert antes <= log.searched_at <= datetime.utcnow()
    assert (log.project_id, log.article_id, log.user_id) == (
        world["p1"], world["a1"], world["user"])
    # Y la salida trae lo verificado: el registro describe, no sustituye.
    assert [v.doi for v in salida.verification.verified] == ["10.1038/nature14539"]


@pytest.mark.asyncio
async def test_una_base_caida_deja_un_registro_parcial_con_su_causa(world):
    salida = await buscar(world, fetch=descubrimiento(crossref=ConnectionError("sin red")))
    (log,) = await logs()
    assert salida.status == "partial" == log.status
    assert log.per_source["crossref"]["status"] == "failed"
    assert log.per_source["crossref"]["error_kind"] == "network"
    assert log.per_source["openalex"]["status"] == "ok"
    assert log.sources == ["openalex", "crossref"]  # se registra lo que se intentó


@pytest.mark.asyncio
async def test_si_el_resolver_no_responde_la_busqueda_es_parcial(world):
    await buscar(world, verification=verif(caido=True))
    (log,) = await logs()
    assert log.status == "partial"
    assert log.verified_count == 0 and log.discarded == {"resolver_unavailable": 2}


@pytest.mark.asyncio
async def test_si_ninguna_base_responde_se_registra_como_fallida(world):
    caida = descubrimiento(crossref=ConnectionError("x"), openalex=ConnectionError("y"))
    salida = await buscar(world, fetch=caida)
    (log,) = await logs()
    assert salida.status == "failed" == log.status
    assert (log.result_count, log.verified_count) == (0, 0)
    assert all(v["status"] == "failed" for v in log.per_source.values())


@pytest.mark.asyncio
async def test_un_error_inesperado_tambien_se_registra_y_se_propaga(world, monkeypatch):
    class Roto(Exception):
        pass

    async def verificador(*a, **k):
        raise Roto("boom")

    import app.platform.capabilities.literature.run as run
    monkeypatch.setattr(run, "verify_candidates", verificador)
    with pytest.raises(Roto):
        await buscar(world)
    (log,) = await logs()
    assert log.status == "failed" and log.query == "deep learning"
    assert log.sources == ["openalex", "crossref"]
    assert "boom" not in json.dumps(log.per_source)  # no se guarda el mensaje del error


@pytest.mark.asyncio
async def test_una_consulta_invalida_no_es_una_busqueda_y_no_deja_registro(world):
    from app.platform.capabilities.literature import LiteratureQueryError, UnknownSourceError
    with pytest.raises(LiteratureQueryError):
        await buscar(world, query="  ")
    with pytest.raises(LiteratureQueryError):
        await buscar(world, query="palabra " * 100)  # un fragmento de texto, no una cadena
    with pytest.raises(UnknownSourceError):
        await buscar(world, sources=["google"])
    assert await logs() == []


# ── Reproducibilidad y privacidad ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_con_el_registro_se_reconstruye_la_consulta(world):
    """Quien lee el registro sabe qué bases, qué cadena, con qué tope y cuándo."""
    await buscar(world, query="  deep   learning  ", sources=["crossref"])
    async with AsyncSessionLocal() as s:
        (log,) = await library.list_searches(s, world["p1"], article_id=world["a1"])
    reg = library.search_record(log)
    assert reg["query"] == "deep learning"  # la cadena normalizada, la que viajó a la base
    assert reg["sources"] == ["crossref"]
    assert reg["filters"]["limit"] == 5
    assert reg["searched_at"].endswith("Z") and datetime.fromisoformat(reg["searched_at"][:-1])
    assert list(reg) == list(library.SEARCH_RECORD_FIELDS)
    json.dumps(reg)  # serializable tal cual


@pytest.mark.asyncio
async def test_no_se_guarda_texto_del_manuscrito_ni_secretos(world):
    # Una base que falla con un mensaje que lleva la URL (con clave y correo).
    sucio = httpx.ConnectError(f"https://x/?mailto={CORREO}&api_key={CLAVE}")
    await buscar(world, fetch=descubrimiento(crossref=sucio),
                 filters={"objeto": object(), "texto": "t" * 5000})
    (log,) = await logs()
    volcado = json.dumps(library.search_record(log)) + json.dumps(log.per_source)
    assert CORREO not in volcado and CLAVE not in volcado
    assert "TEXTO-DEL-MANUSCRITO" not in volcado
    assert "objeto" not in log.filters and len(log.filters["texto"]) == 200
    assert "user_id" not in library.search_record(log)


def test_los_filtros_se_sanean():
    assert sanitize_filters({"a": 1, "b": [1, "x", {"no": 1}], 3: "k", "c": {"d": 1}}) == {
        "a": 1, "b": [1, "x"]}
    assert sanitize_filters(None) == {}


# ── Aislamiento por proyecto ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_el_registro_no_cruza_proyectos(world):
    await buscar(world)
    await buscar(world, project_id=world["p2"], article_id=world["a2"], user_id=world["otra"])
    async with AsyncSessionLocal() as s:
        p1 = await library.list_searches(s, world["p1"])
        p2 = await library.list_searches(s, world["p2"])
    assert [log.project_id for log in p1] == [world["p1"]]
    assert [log.project_id for log in p2] == [world["p2"]]


# ── Traza ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_la_busqueda_se_anota_en_el_paso_sin_tocar_al_agente(world):
    with ex.collecting() as acumulador:
        salida = await buscar(world)
    (anotada,) = acumulador.searches
    assert anotada["search_id"] == str(salida.log.id)
    assert set(anotada) == set(ex.CAMPOS_BUSQUEDA)
    assert anotada["status"] == "completed" and anotada["verified_count"] == 1


@pytest.mark.asyncio
async def test_las_busquedas_fallidas_tambien_quedan_en_la_traza(world):
    caida = descubrimiento(crossref=ConnectionError("x"), openalex=ConnectionError("y"))
    with ex.collecting() as acumulador:
        await buscar(world, fetch=caida)
    assert [s["status"] for s in acumulador.searches] == ["failed"]


@pytest.mark.asyncio
async def test_fuera_de_un_paso_anotar_no_hace_nada(world):
    assert ex.current() is None
    await buscar(world)  # no revienta


def test_la_cadena_de_integridad_cubre_las_busquedas_y_la_v1_sigue_valiendo():
    base = dict(article_id="a", project_id="p", agent_name="investigador", step_index=0,
                iteration=0, status="completed", model=None, params={}, rag_sources=[],
                tokens_in=0, tokens_out=0, latency_ms=0.0)
    sin = {**base, "searches": []}
    con = {**base, "searches": [{"search_id": "s1", "query": "q"}]}
    # v2: añadir o quitar una búsqueda cambia el hash.
    assert ex.compute_hash(sin, None, version=2) != ex.compute_hash(con, None, version=2)
    # v1: las cadenas ya escritas no incluían `searches` y se verifican igual que antes.
    assert ex.compute_hash(sin, None, version=1) == ex.compute_hash(con, None, version=1)
    assert '"searches"' not in ex.canonical_form(con, version=1)
    # Ausente y vacío son lo mismo.
    assert ex.compute_hash(base, None, version=2) == ex.compute_hash(sin, None, version=2)


def test_una_cadena_v1_ya_escrita_sigue_verificandose():
    campos = dict(article_id="a", project_id="p", agent_name="investigador", step_index=0,
                  iteration=0, status="completed", params={}, rag_sources=[],
                  tokens_in=0, tokens_out=0, latency_ms=0.0)

    class Paso:
        searches = []
        hash_version = 1
        prev_hash = None
        content_hash = ex.compute_hash(campos, None, version=1)
        step_index = 0
        agent_name = "investigador"

    for k, v in campos.items():
        setattr(Paso, k, v)
    assert ex.verify_chain([Paso])["status"] == "intacta"


# ── API: lectura, traza y exportación ───────────────────────────────────────

@pytest.fixture
def client():
    from app.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _token(ac, email):
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": "Contrasena-1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_endpoint_searches_exige_proyecto_y_aisla(world, client):
    await buscar(world)
    await buscar(world, project_id=world["p2"], article_id=world["a2"], user_id=world["otra"])
    async with client as ac:
        h = await _token(ac, "autora@ejemplo.com")
        url = f"/api/v1/agents/{world['a1']}/searches"
        # Sin proyecto activo: 400 (get_project_context obligatorio).
        assert (await ac.get(url, headers=h)).status_code == 400
        ok = await ac.get(url, headers={**h, "X-Project-Id": str(world["p1"])})
        assert ok.status_code == 200, ok.text
        cuerpo = ok.json()
        assert cuerpo["schema_version"] == library.SEARCH_RECORD_VERSION
        assert [s["query"] for s in cuerpo["searches"]] == ["deep learning"]
        # Un proyecto ajeno: 404, sin confirmar que existe.
        assert (await ac.get(url, headers={**h, "X-Project-Id": str(world["p2"])})).status_code == 404
        # El artículo de otra persona/proyecto no se lee con mi proyecto.
        ajeno = f"/api/v1/agents/{world['a2']}/searches"
        assert (await ac.get(ajeno, headers={**h, "X-Project-Id": str(world["p1"])})).status_code in (403, 404)


@pytest.mark.asyncio
async def test_la_traza_y_el_historial_incluyen_la_busqueda(world, client):
    with ex.collecting() as acumulador:
        await buscar(world)
    async with AsyncSessionLocal() as s:
        campos = dict(article_id=world["a1"], project_id=world["p1"], agent_name="investigador",
                      step_index=0, iteration=0, status="completed", params={}, rag_sources=[],
                      tokens_in=0, tokens_out=0, latency_ms=0.0, searches=acumulador.searches)
        campos["hash_version"] = ex.CANON_VERSION
        campos["content_hash"] = ex.compute_hash(campos, None)
        s.add(AgentRunStepModel(**campos))
        await s.commit()
    async with client as ac:
        h = {**await _token(ac, "autora@ejemplo.com"), "X-Project-Id": str(world["p1"])}
        explain = (await ac.get(f"/api/v1/agents/{world['a1']}/explain", headers=h)).json()
        assert explain["steps"][0]["searches"][0]["query"] == "deep learning"
        assert explain["searches"][0]["status"] == "completed"
        assert explain["searches"][0]["id"] == explain["steps"][0]["searches"][0]["search_id"]
        integ = (await ac.get(f"/api/v1/agents/{world['a1']}/integrity", headers=h)).json()
        assert integ["status"] == "intacta"
        hist = (await ac.get(f"/api/v1/agents/{world['a1']}/history", headers=h)).json()
        detalle = (await ac.get(
            f"/api/v1/agents/{world['a1']}/history/{hist['executions'][0]['id']}", headers=h)).json()
        assert detalle["searches"][0]["query"] == "deep learning"


@pytest.mark.asyncio
async def test_la_exportacion_incluye_las_busquedas_con_formato_estable(world, client):
    await buscar(world)
    await buscar(world, query="otra cadena", fetch=descubrimiento(crossref=ConnectionError("x")))
    async with client as ac:
        h = {**await _token(ac, "autora@ejemplo.com"), "X-Project-Id": str(world["p1"])}
        r = await ac.get(f"/api/v1/agents/{world['a1']}/export.jsonl", headers=h)
    assert r.status_code == 200
    lineas = [json.loads(linea) for linea in r.text.splitlines()]
    cabecera = lineas[0]
    busquedas = [linea for linea in lineas if linea.get("type") == "search"]
    assert cabecera["type"] == "header" and cabecera["searches"] == 2
    assert cabecera["schema_version"] == EXPORT_SCHEMA_VERSION == 2
    assert cabecera["search_schema"] == list(library.SEARCH_RECORD_FIELDS)
    assert cabecera["search_schema_version"] == library.SEARCH_RECORD_VERSION
    assert "searches" in EXPORT_SCHEMA  # los pasos llevan sus búsquedas: entran en el hash
    # Formato estable: type + los campos declarados, en ese orden, y nada más.
    for b in busquedas:
        assert list(b) == ["type", *library.SEARCH_RECORD_FIELDS]
    assert [b["query"] for b in busquedas] == ["deep learning", "otra cadena"]
    assert [b["status"] for b in busquedas] == ["completed", "partial"]
    assert busquedas[0]["sources"] == ["openalex", "crossref"]
    # Nada privado en el fichero.
    assert CORREO not in r.text and CLAVE not in r.text and "TEXTO-DEL-MANUSCRITO" not in r.text


@pytest.mark.asyncio
async def test_la_exportacion_no_incluye_busquedas_de_otro_articulo(world, client):
    await buscar(world, project_id=world["p2"], article_id=world["a2"], user_id=world["otra"])
    async with client as ac:
        h = {**await _token(ac, "autora@ejemplo.com"), "X-Project-Id": str(world["p1"])}
        r = await ac.get(f"/api/v1/agents/{world['a1']}/export.jsonl", headers=h)
    lineas = [json.loads(linea) for linea in r.text.splitlines()]
    assert lineas[0]["searches"] == 0 and len(lineas) == 1
