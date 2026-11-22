"""SPEC-034 / T22.4 — DOI de PDFs subidos y edición manual de metadatos (AC4). Sin red real.

El resolver sale por la puerta de egress (`safe_get`), que aquí se sustituye por un doble: así
se prueba también que la subida usa esa puerta y no abre conexiones propias. Lo que se vigila:
que subir crea la ficha, que solo se verifica si el registro coincide, que un resolver caído
nunca verifica ni rompe la subida, que una ficha sin verificar no es citable, que el DOI del
autor registra quién y cuándo, y que el aislamiento por proyecto se mantiene.
"""
import io
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

TEST_DB_PATH = (ROOT_DIR / "tests" / "test_library_upload_doi.db").resolve()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import ProjectModel, UserModel, UserRole  # noqa: E402
from app.platform import egress, library, library_upload as lu  # noqa: E402
from app.platform.publication_gate import reference_resolver as rr  # noqa: E402

TITULO = "Attention is all you need"
AUTORES = "Ashish Vaswani, Noam Shazeer, Niki Parmar"
DOI = "10.5555/3295222.3295349"
ITEM = {"DOI": DOI, "title": [TITULO], "type": "proceedings-article",
        "author": [{"family": "Vaswani"}, {"family": "Shazeer"}, {"family": "Parmar"}],
        "issued": {"date-parts": [[2017]]}, "container-title": ["NeurIPS"]}


class Resp:
    def __init__(self, status=200, data=None):
        self.status_code, self._data, self.text, self.headers = status, data, "", {}

    def json(self):
        return self._data


class Registro:
    """Crossref simulado: la búsqueda por título devuelve `items`; por DOI, el que se conozca."""

    def __init__(self, items=(ITEM,), caido=False):
        self.items, self.caido, self.calls = list(items), caido, []

    async def __call__(self, url, **kw):
        self.calls.append(url)
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


async def _nosleep(_):
    pass


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
        ids = {"user": user.id, "otra": otra.id, "p1": p1.id, "p2": p2.id}
    yield ids
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def egreso(monkeypatch):
    """Todo el egress del test pasa por este doble; nada abre un socket."""
    registro = Registro()
    quienes = []

    async def safe_get(url, *, quien, params=None, headers=None, timeout=10.0, **kw):
        quienes.append(quien)
        return await registro(url, params=params)

    monkeypatch.setattr(egress, "safe_get", safe_get)
    registro.quienes = quienes
    return registro


async def subir(world, *, project="p1", title=TITULO, authors=AUTORES, doc_id="d1", resolver=None):
    async with AsyncSessionLocal() as s:
        return await lu.register_uploaded_document(
            s, world[project], doc_id=doc_id, filename="paper.pdf", title=title,
            authors=authors, added_by=world["user"], resolver=resolver,
        )


# ── Servicio ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_subir_crea_la_ficha_y_resuelve_el_doi_por_titulo_y_autores(world, egreso):
    r = await subir(world)
    d = r["document"]
    assert r["resolution"] == lu.RESOLVED
    assert d.verified and d.verification_method == "doi_resolved" and d.verified_at is not None
    assert d.doi == DOI and d.verified_by is None  # lo verificó el sistema
    assert (d.doc_id, d.source_db, d.text_status, d.curation_status) == (
        "d1", "manual", "full_text", "accepted")
    assert d.year == 2017 and d.journal == "NeurIPS"  # completado desde el registro
    assert library.is_citable(d)
    assert egreso.quienes and set(egreso.quienes) == {egress.QUIEN_LITERATURA}


@pytest.mark.asyncio
async def test_sin_coincidencia_la_ficha_queda_sin_verificar_y_no_es_citable(world, egreso):
    egreso.items = []
    r = await subir(world)
    d = r["document"]
    assert r["resolution"] == lu.UNRESOLVED
    assert not d.verified and d.doi is None and d.verification_method is None
    assert not library.is_citable(d)
    assert [x.id for x in await _citables(world["p1"])] == []


@pytest.mark.asyncio
async def test_un_registro_que_no_coincide_no_verifica(world, egreso):
    egreso.items = [{**ITEM, "title": ["Un artículo distinto sobre otra cosa"]}]
    r = await subir(world)
    assert r["resolution"] == lu.UNRESOLVED and not r["document"].verified


@pytest.mark.asyncio
async def test_resolver_caido_no_verifica_ni_rompe_la_subida(world, egreso):
    egreso.caido = True
    r = await subir(world, resolver=rr.ResolverConfig(retries=1, backoff_s=0.0))
    assert r["resolution"] == lu.UNAVAILABLE
    assert not r["document"].verified and not library.is_citable(r["document"])


@pytest.mark.asyncio
async def test_un_error_inesperado_tampoco_verifica(world, monkeypatch):
    async def roto(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(lu, "verify_candidates", roto)
    r = await subir(world)
    assert r["resolution"] == lu.UNAVAILABLE and not r["document"].verified


@pytest.mark.asyncio
async def test_sin_titulo_o_autores_no_se_busca_y_queda_sin_verificar(world, egreso):
    r = await subir(world, title="", authors="")
    assert r["resolution"] == lu.NO_METADATA and r["document"].title == "paper"
    assert not r["document"].verified and egreso.calls == []


@pytest.mark.asyncio
async def test_doi_ya_en_la_biblioteca_deja_la_ficha_sin_verificar(world):
    await subir(world, doc_id="d1")
    r = await subir(world, doc_id="d2")
    assert r["resolution"] == lu.DUPLICATE_DOI
    assert not r["document"].verified and r["document"].doi is None


@pytest.mark.asyncio
async def test_el_autor_aporta_el_doi_con_quien_y_cuando(world, egreso):
    egreso.items = []
    ficha = (await subir(world))["document"]
    async with AsyncSessionLocal() as s:
        d = await lu.update_metadata(s, world["p1"], ficha.id, {"doi": "https://doi.org/10.1/ABC"},
                                     user_id=world["user"])
    assert d.doi == "10.1/abc"
    assert d.verified and d.verification_method == "author_supplied"
    assert d.verified_by == world["user"] and d.verified_at is not None
    assert library.is_citable(d)


@pytest.mark.asyncio
async def test_editar_metadatos_sin_doi_no_verifica(world, egreso):
    egreso.items = []
    ficha = (await subir(world))["document"]
    async with AsyncSessionLocal() as s:
        d = await lu.update_metadata(
            s, world["p1"], ficha.id,
            {"title": "Otro título", "authors": "A. Uno; B. Dos", "year": 2020, "journal": "J"},
            user_id=world["user"])
    assert (d.title, d.authors, d.year, d.journal) == ("Otro título", ["A. Uno", "B. Dos"], 2020, "J")
    assert not d.verified and not library.is_citable(d)


@pytest.mark.asyncio
async def test_cambiar_el_doi_lo_reverifica_como_del_autor_y_vaciarlo_retira_la_verificacion(world):
    ficha = (await subir(world))["document"]  # verificada por el sistema
    async with AsyncSessionLocal() as s:
        d = await lu.update_metadata(s, world["p1"], ficha.id, {"doi": "10.9/otro"}, user_id=world["user"])
        assert d.verification_method == "author_supplied" and d.verified_by == world["user"]
        d = await lu.update_metadata(s, world["p1"], ficha.id, {"doi": ""}, user_id=world["user"])
    assert d.doi is None and not d.verified and d.verification_method is None
    assert d.verified_at is None and d.verified_by is None and not library.is_citable(d)


@pytest.mark.asyncio
async def test_doi_repetido_en_el_proyecto_se_rechaza_sin_cambiar_nada(world):
    await subir(world, doc_id="d1")  # se queda con DOI
    async with AsyncSessionLocal() as s:
        otra = await library.add_document(s, world["p1"], title="x", authors=[], doc_id="d2")
        with pytest.raises(library.DuplicateDocumentError):
            await lu.update_metadata(s, world["p1"], otra.id, {"doi": DOI, "title": "cambiado"},
                                     user_id=world["user"])
        refrescada = await library.get_document(s, world["p1"], otra.id)
    assert refrescada.title == "x" and refrescada.doi is None


@pytest.mark.asyncio
async def test_editar_la_ficha_de_otro_proyecto_no_existe(world):
    ficha = (await subir(world))["document"]
    async with AsyncSessionLocal() as s:
        assert await lu.update_metadata(s, world["p2"], ficha.id, {"doi": "10.1/x"},
                                        user_id=world["otra"]) is None


@pytest.mark.asyncio
async def test_un_documento_sin_verificar_no_llega_a_sources_del_investigador(world, egreso):
    """Misma clasificación que usa el Investigador: sin verificar => solo contexto."""
    egreso.items = []
    await subir(world, doc_id="d1")
    async with AsyncSessionLocal() as s:
        fichas = await library.documents_by_rag_id(s, world["p1"], ["d1"])
        assert not library.is_citable(fichas["d1"])
        assert await library.citable_documents(s, world["p1"]) == []


async def _citables(project):
    async with AsyncSessionLocal() as s:
        return await library.citable_documents(s, project)


# ── API ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from app.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _headers(ac, email, project):
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": "Contrasena-1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}", "X-Project-Id": str(project)}


@pytest.fixture
def rag_falso(monkeypatch):
    import app.routers.agents as agents

    async def ensure(*a, **k):
        return True

    async def upsert(*a, **k):
        return 3

    monkeypatch.setattr(agents, "ensure_collection", ensure)
    monkeypatch.setattr(agents, "upsert_chunks", upsert)
    monkeypatch.setattr(agents, "extract_doc_metadata",
                        lambda *a, **k: {"title": TITULO, "authors": AUTORES})


@pytest.mark.asyncio
async def test_api_subir_devuelve_la_ficha_y_el_estado_de_resolucion(world, client, rag_falso):
    async with client as ac:
        h = await _headers(ac, "autora@ejemplo.com", world["p1"])
        r = await ac.post("/api/v1/agents/rag/library/upload", headers=h,
                          files={"file": ("paper.txt", io.BytesIO(b"contenido del paper"), "text/plain")})
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        assert cuerpo["doi_resolution"] == "resolved"
        assert cuerpo["library_document"]["doi"] == DOI and cuerpo["library_document"]["citable"]
        lista = await ac.get("/api/v1/agents/rag/library/records", headers=h)
        assert [d["doi"] for d in lista.json()["documents"]] == [DOI]
        h2 = await _headers(ac, "otra@ejemplo.com", world["p2"])
        assert (await ac.get("/api/v1/agents/rag/library/records", headers=h2)).json()["documents"] == []


@pytest.mark.asyncio
async def test_api_editar_y_aportar_doi(world, client, rag_falso, egreso):
    egreso.items = []
    async with client as ac:
        h = await _headers(ac, "autora@ejemplo.com", world["p1"])
        up = await ac.post("/api/v1/agents/rag/library/upload", headers=h,
                           files={"file": ("paper.txt", io.BytesIO(b"contenido"), "text/plain")})
        ficha = up.json()["library_document"]
        assert up.json()["doi_resolution"] == "unresolved" and not ficha["verified"]
        url = f"/api/v1/agents/rag/library/records/{ficha['id']}"
        r = await ac.patch(url, headers=h, json={"doi": "10.1/ABC", "year": 2017})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["doi"] == "10.1/abc" and d["verification_method"] == "author_supplied"
        assert d["verified_by"] == str(world["user"]) and d["verified_at"] and d["citable"]
        h2 = await _headers(ac, "otra@ejemplo.com", world["p2"])
        assert (await ac.patch(url, headers=h2, json={"title": "x"})).status_code == 404
        assert (await ac.patch(url, headers=h, json={"title": "  "})).status_code == 422
