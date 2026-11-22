"""SPEC-034 / T22.11 — POST /agents/rag/library/search (AC12). Sin red real.

Se vigila: que apagado no hace ninguna petición; que solo se guardan candidatos
**verificados**; que un DOI ya presente en el proyecto (en cualquier estado) no se vuelve a
crear; que una base caída no oculta a las demás ni filtra su URL; el aislamiento entre
proyectos, el limitador y los permisos.
"""
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

TEST_DB_PATH = (ROOT_DIR / "tests" / "test_library_discovery_endpoint.db").resolve()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.core.rate_limit import literature_search_limiter  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import ProjectModel, SearchLogModel, UserModel, UserRole  # noqa: E402
from app.platform import egress, library  # noqa: E402
from app.platform.publication_gate import reference_resolver as rr  # noqa: E402

DOI = "10.1038/nature14539"
OPENALEX = {"results": [
    {"id": "https://openalex.org/W1", "doi": f"https://doi.org/{DOI}",
     "title": "Deep learning", "publication_year": 2015, "publication_date": "2015-05-27",
     "authorships": [{"author": {"display_name": "Yann LeCun"}}],
     "primary_location": {"source": {"display_name": "Nature"},
                          "pdf_url": "https://example.org/dl.pdf"},
     "open_access": {"oa_url": "https://example.org/dl.pdf"}},
    {"id": "https://openalex.org/W2", "doi": "https://doi.org/10.9999/inventado",
     "title": "Un articulo que no existe", "publication_year": 2020,
     "authorships": [{"author": {"display_name": "Nadie"}}], "primary_location": None},
]}
CROSSREF_ITEM = {"DOI": DOI, "title": ["Deep learning"], "type": "journal-article",
                 "author": [{"family": "LeCun", "given": "Yann"}],
                 "issued": {"date-parts": [[2015]]}, "container-title": ["Nature"]}


class Resp:
    def __init__(self, status=200, data=None):
        self.status_code, self._data, self.text, self.headers = status, data, "", {}

    def json(self):
        return self._data


class Red:
    """Doble de `egress.safe_get`: cuenta peticiones y simula bases caídas."""

    def __init__(self):
        self.calls = []
        self.crossref_caido = False
        self.openalex_caido = False

    async def __call__(self, url, *, quien=None, params=None, headers=None, timeout=10.0, **kw):
        self.calls.append(url)
        if url == rr.OPENALEX:
            if self.openalex_caido:
                raise ConnectionError("https://api.openalex.org/works?api_key=SECRETO caído")
            return Resp(200, OPENALEX)
        if url == rr.CROSSREF:
            if self.crossref_caido:
                raise ConnectionError("https://api.crossref.org/works?mailto=secreto@x.org caído")
            return Resp(200, {"status": "ok", "message": {"items": []}})
        if url == rr.CROSSREF + "/" + DOI:
            return Resp(200, {"message": CROSSREF_ITEM})
        return Resp(404)


@pytest.fixture(autouse=True)
def red(monkeypatch):
    r = Red()
    monkeypatch.setattr(egress, "safe_get", r)
    monkeypatch.setattr(settings, "LITERATURE_DISCOVERY_ENABLED", True)
    monkeypatch.setattr(settings, "LITERATURE_RETRIES", 0)
    monkeypatch.setattr(settings, "LITERATURE_BACKOFF_S", 0.0)
    monkeypatch.setattr(settings, "LITERATURE_SEARCH_RATELIMIT_MAX", 50)
    literature_search_limiter.reset()
    return r


@pytest_asyncio.fixture
async def world():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as s:
        mk = lambda email, role: UserModel(  # noqa: E731
            email=email, hashed_password=hash_password("Contrasena-1234"),
            full_name=email, role=role, is_active=True)
        user, otra, lector = (mk("autora@ejemplo.com", UserRole.REDACTOR),
                              mk("otra@ejemplo.com", UserRole.REDACTOR),
                              mk("lector@ejemplo.com", UserRole.LECTOR))
        s.add_all([user, otra, lector])
        await s.commit()
        p1 = ProjectModel(name="P1", owner_id=user.id)
        p2 = ProjectModel(name="P2", owner_id=otra.id)
        s.add_all([p1, p2])
        await s.commit()
        ids = {"user": user.id, "p1": p1.id, "p2": p2.id}
    yield ids
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def client():
    from app.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _headers(ac, email, project):
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": "Contrasena-1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}", "X-Project-Id": str(project)}


URL = "/api/v1/agents/rag/library/search"


async def _docs(project):
    async with AsyncSessionLocal() as s:
        return await library.list_documents(s, project)


@pytest.mark.asyncio
async def test_apagado_no_hace_peticiones_ni_registra_nada(world, client, red, monkeypatch):
    monkeypatch.setattr(settings, "LITERATURE_DISCOVERY_ENABLED", False)
    async with client as ac:
        h = await _headers(ac, "autora@ejemplo.com", world["p1"])
        r = await ac.post(URL, headers=h, json={"query": "deep learning"})
        cfg = await ac.get(URL + "/config", headers=h)
    assert r.status_code == 200
    assert r.json()["enabled"] is False and "desactivado" in r.json()["message"].lower()
    assert r.json()["new_candidates"] == 0
    assert cfg.json()["enabled"] is False
    assert red.calls == []
    assert await _docs(world["p1"]) == []
    async with AsyncSessionLocal() as s:
        assert list(await s.scalars(select(SearchLogModel))) == []


def test_flag_apagado_por_defecto():
    from app.core.config import Settings
    assert Settings.model_fields["LITERATURE_DISCOVERY_ENABLED"].default is False


@pytest.mark.asyncio
async def test_guarda_solo_verificados_con_sus_metadatos(world, client, red):
    async with client as ac:
        h = await _headers(ac, "autora@ejemplo.com", world["p1"])
        r = await ac.post(URL, headers=h, json={"query": "deep learning"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["new_candidates"] == 1 and body["unverified_discarded"] == 1
    assert {s["db"]: s["status"] for s in body["sources"]} == {"openalex": "ok", "crossref": "ok"}
    docs = await _docs(world["p1"])
    assert [d.doi for d in docs] == [DOI]
    d = docs[0]
    assert (d.curation_status, d.verified, d.year, d.journal, d.source_db) == (
        "candidate", True, 2015, "Nature", "openalex")
    assert "LeCun" in " ".join(d.authors) and d.open_access_url == "https://example.org/dl.pdf"
    # Y aparece en el panel de candidatos.
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        h = await _headers(ac, "autora@ejemplo.com", world["p1"])
        recs = (await ac.get("/api/v1/agents/rag/library/records", headers=h)).json()["documents"]
    assert recs[0]["curation_status"] == "candidate"


@pytest.mark.asyncio
@pytest.mark.parametrize("estado", ["candidate", "accepted", "discarded"])
async def test_doi_ya_en_la_biblioteca_en_cualquier_estado_no_se_vuelve_a_crear(
        world, client, estado):
    async with AsyncSessionLocal() as s:
        doc = await library.add_document(s, world["p1"], doi=DOI, title="Deep learning",
                                         curation_status="candidate")
        if estado != "candidate":
            await library.set_curation(s, world["p1"], doc.id, estado)
    async with client as ac:
        h = await _headers(ac, "autora@ejemplo.com", world["p1"])
        body = (await ac.post(URL, headers=h, json={"query": "deep learning"})).json()
    assert body["new_candidates"] == 0 and body["already_in_library"] == 1
    docs = await _docs(world["p1"])
    assert len(docs) == 1 and docs[0].curation_status == estado


@pytest.mark.asyncio
async def test_repetir_la_busqueda_no_duplica(world, client):
    async with client as ac:
        h = await _headers(ac, "autora@ejemplo.com", world["p1"])
        a = (await ac.post(URL, headers=h, json={"query": "deep learning"})).json()
        b = (await ac.post(URL, headers=h, json={"query": "deep learning"})).json()
    assert (a["new_candidates"], b["new_candidates"]) == (1, 0)
    assert len(await _docs(world["p1"])) == 1


@pytest.mark.asyncio
async def test_aislamiento_entre_proyectos(world, client):
    # El mismo DOI en el proyecto 2 no cuenta como «ya está» en el proyecto 1.
    async with AsyncSessionLocal() as s:
        await library.add_document(s, world["p2"], doi=DOI, title="Deep learning",
                                   curation_status="accepted")
    async with client as ac:
        h = await _headers(ac, "autora@ejemplo.com", world["p1"])
        body = (await ac.post(URL, headers=h, json={"query": "deep learning"})).json()
        # Quien no es del proyecto 1 no puede buscar en él.
        h2 = await _headers(ac, "otra@ejemplo.com", world["p1"])
        denegado = await ac.post(URL, headers=h2, json={"query": "deep learning"})
    assert body["new_candidates"] == 1
    assert [d.curation_status for d in await _docs(world["p1"])] == ["candidate"]
    assert [d.curation_status for d in await _docs(world["p2"])] == ["accepted"]
    assert denegado.status_code in (403, 404)
    async with AsyncSessionLocal() as s:
        logs = list(await s.scalars(select(SearchLogModel)))
    assert {log.project_id for log in logs} == {world["p1"]}


@pytest.mark.asyncio
async def test_una_base_caida_no_oculta_a_las_demas_ni_filtra_su_url(world, client, red):
    red.crossref_caido = True
    async with client as ac:
        h = await _headers(ac, "autora@ejemplo.com", world["p1"])
        r = await ac.post(URL, headers=h, json={"query": "deep learning"})
    body = r.json()
    estados = {s["db"]: s for s in body["sources"]}
    assert estados["openalex"]["status"] == "ok" and estados["crossref"]["status"] == "failed"
    assert estados["crossref"]["message"]
    assert body["status"] == "partial" and body["new_candidates"] == 1
    assert "secreto" not in r.text.lower() and "api_key" not in r.text


@pytest.mark.asyncio
async def test_todas_caidas_falla_cerrada_sin_guardar(world, client, red):
    red.crossref_caido = red.openalex_caido = True
    async with client as ac:
        h = await _headers(ac, "autora@ejemplo.com", world["p1"])
        body = (await ac.post(URL, headers=h, json={"query": "deep learning"})).json()
    assert body["status"] == "failed" and body["new_candidates"] == 0
    assert "ninguna base" in body["message"].lower()
    assert await _docs(world["p1"]) == []


@pytest.mark.asyncio
async def test_bases_y_consulta_se_validan(world, client):
    async with client as ac:
        h = await _headers(ac, "autora@ejemplo.com", world["p1"])
        assert (await ac.post(URL, headers=h, json={"query": "x", "sources": ["pubmed"]})).status_code == 422
        assert (await ac.post(URL, headers=h, json={"query": "   "})).status_code == 422
        # Un fragmento de manuscrito no es una cadena de búsqueda: no sale a terceros.
        assert (await ac.post(URL, headers=h, json={"query": "texto " * 100})).status_code == 422
        r = await ac.post(URL, headers=h, json={"query": "deep learning", "sources": ["openalex"]})
    assert [s["db"] for s in r.json()["sources"]] == ["openalex"]


@pytest.mark.asyncio
async def test_limitador_y_permisos(world, client, monkeypatch, red):
    monkeypatch.setattr(settings, "LITERATURE_SEARCH_RATELIMIT_MAX", 1)
    async with client as ac:
        h = await _headers(ac, "autora@ejemplo.com", world["p1"])
        assert (await ac.post(URL, headers=h, json={"query": "deep learning"})).status_code == 200
        antes = len(red.calls)
        r = await ac.post(URL, headers=h, json={"query": "deep learning"})
        assert r.status_code == 429 and "Retry-After" in r.headers
        assert len(red.calls) == antes
        hl = await _headers(ac, "lector@ejemplo.com", world["p1"])
        assert (await ac.post(URL, headers=hl, json={"query": "deep learning"})).status_code in (403, 404)
