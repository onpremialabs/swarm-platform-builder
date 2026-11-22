"""SPEC-034 / T22.8 — curación de candidatos (AC3) e importación BibTeX/DOI (AC9). Sin red real."""
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

TEST_DB_PATH = (ROOT_DIR / "tests" / "test_library_curation_import.db").resolve()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import ProjectModel, UserModel, UserRole  # noqa: E402
from app.platform import egress, library, library_import  # noqa: E402
from app.platform.publication_gate import reference_resolver as rr  # noqa: E402

TITULO = "Attention is all you need"
DOI = "10.5555/3295222.3295349"
ITEM = {"DOI": DOI, "title": [TITULO], "type": "proceedings-article",
        "author": [{"family": "Vaswani"}, {"family": "Shazeer"}],
        "issued": {"date-parts": [[2017]]}, "container-title": ["NeurIPS"]}

BIBTEX = """
@inproceedings{vaswani2017,
  title = {Attention is all you need},
  author = {Vaswani, Ashish and Shazeer, Noam},
  year = {2017}, booktitle = {NeurIPS},
  doi = {10.5555/3295222.3295349}
}
@article{sindoi,
  title = "Un articulo sin DOI",
  author = {Perez, Ana},
  year = 2020
}
@article{sintitulo, year = {2021}}
@comment{ignorado}
"""


class Resp:
    def __init__(self, status=200, data=None):
        self.status_code, self._data, self.text, self.headers = status, data, "", {}

    def json(self):
        return self._data


class Registro:
    def __init__(self, items=(ITEM,), caido=False):
        self.items, self.caido = list(items), caido

    async def __call__(self, url, **kw):
        if self.caido:
            raise ConnectionError("sin red")
        if url == rr.CROSSREF:
            return Resp(200, {"message": {"items": self.items}})
        if url.startswith(rr.CROSSREF + "/"):
            doi = url[len(rr.CROSSREF) + 1:]
            for it in self.items:
                if it["DOI"].lower() == doi.lower():
                    return Resp(200, {"message": it})
            return Resp(404)
        if url == rr.OPENALEX:
            return Resp(200, {"results": []})
        return Resp(404)


@pytest_asyncio.fixture
async def world():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
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
        ids = {"user": user.id, "p1": p1.id, "p2": p2.id}
    yield ids
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def egreso(monkeypatch):
    registro = Registro()

    async def safe_get(url, *, quien, params=None, headers=None, timeout=10.0, **kw):
        return await registro(url, params=params)

    monkeypatch.setattr(egress, "safe_get", safe_get)
    return registro


@pytest.fixture
def client():
    from app.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _headers(ac, email, project):
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": "Contrasena-1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}", "X-Project-Id": str(project)}


# ── Parsers ──────────────────────────────────────────────────────────────────

def test_parse_bibtex_lee_llaves_comillas_numeros_y_ignora_comment():
    e = library_import.parse_bibtex(BIBTEX)
    assert [x["_key"] for x in e] == ["vaswani2017", "sindoi", "sintitulo"]
    assert e[0]["doi"] == DOI and e[0]["booktitle"] == "NeurIPS"
    assert e[1]["title"] == "Un articulo sin DOI" and e[1]["year"] == "2020"


def test_parse_dois_normaliza_y_no_repite():
    texto = f"https://doi.org/{DOI.upper()}, {DOI}\nbasura 10.1/ab"
    assert library_import.parse_dois(texto) == [DOI]


# ── Servicio ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bibtex_verifica_el_que_resuelve_y_deja_sin_verificar_el_resto(world):
    async with AsyncSessionLocal() as s:
        res = await library_import.import_bibtex(s, world["p1"], BIBTEX, added_by=world["user"])
    estados = {r["ref"]: (r["status"], r["verified"]) for r in res}
    assert estados == {"vaswani2017": ("imported", True), "sindoi": ("imported", False),
                       "sintitulo": ("invalid", False)}
    async with AsyncSessionLocal() as s:
        docs = await library.list_documents(s, world["p1"])
        citables = await library.citable_documents(s, world["p1"])
    assert len(docs) == 2 and [d.doi for d in citables] == [DOI]
    sin = next(d for d in docs if d.doi is None)
    assert not sin.verified and sin.curation_status == "accepted"


@pytest.mark.asyncio
async def test_bibtex_con_resolver_caido_no_verifica_nada(world, egreso):
    egreso.caido = True
    async with AsyncSessionLocal() as s:
        res = await library_import.import_bibtex(s, world["p1"], BIBTEX, added_by=world["user"])
    assert not any(r["verified"] for r in res)
    async with AsyncSessionLocal() as s:
        assert await library.citable_documents(s, world["p1"]) == []


@pytest.mark.asyncio
async def test_lista_de_dois_trae_metadatos_del_registro_y_marca_duplicados(world):
    async with AsyncSessionLocal() as s:
        res = await library_import.import_dois(s, world["p1"], f"{DOI}\n10.9999/inexistente",
                                               added_by=world["user"])
        assert [(r["status"], r["verified"]) for r in res] == [("imported", True), ("invalid", False)]
        doc = (await library.list_documents(s, world["p1"]))[0]
        assert (doc.title, doc.year, doc.journal, doc.verification_method) == (
            TITULO, 2017, "NeurIPS", "doi_resolved")
        otra = await library_import.import_dois(s, world["p1"], DOI)
    assert otra[0]["status"] == "duplicate"


# ── API ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_importar_y_curar(world, client):
    async with client as ac:
        h = await _headers(ac, "autora@ejemplo.com", world["p1"])
        r = await ac.post("/api/v1/agents/rag/library/import", headers=h, json={"bibtex": BIBTEX})
        assert r.status_code == 200, r.text
        assert r.json()["imported"] == 2
        assert (await ac.post("/api/v1/agents/rag/library/import", headers=h, json={})).status_code == 422
        assert (await ac.post("/api/v1/agents/rag/library/import", headers=h,
                              json={"dois": "nada"})).status_code == 422
        docs = (await ac.get("/api/v1/agents/rag/library/records", headers=h)).json()["documents"]
        doc = next(d for d in docs if d["doi"] == DOI)
        url = f"/api/v1/agents/rag/library/records/{doc['id']}/curation"
        r = await ac.post(url, headers=h, json={"status": "accepted", "must_cite": True})
        assert r.status_code == 200 and r.json()["must_cite"] and r.json()["curation_status"] == "accepted"
        r = await ac.post(url, headers=h, json={"status": "discarded", "must_cite": True})
        assert r.json()["curation_status"] == "discarded" and not r.json()["must_cite"]
        assert (await ac.post(url, headers=h, json={"status": "otro"})).status_code == 422
        h2 = await _headers(ac, "otra@ejemplo.com", world["p2"])
        assert (await ac.post(url, headers=h2, json={"status": "accepted"})).status_code == 404
