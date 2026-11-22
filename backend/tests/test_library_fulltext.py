"""SPEC-034 / T22.10 — PDF de acceso abierto al aceptar un candidato y estado «solo resumen» (AC11).

Sin red real: `egress.safe_get` y el índice se sustituyen por dobles. Lo que se vigila: que la
descarga sale por `safe_get` con `quien="literature_discovery"` y solo hacia `open_access_url`,
que se valida (magic bytes, tipo, tamaño), que cualquier fallo deja la ficha aceptada como
`abstract_only` sin romper la aceptación, y que subir el PDF después la pasa a `full_text`.
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

TEST_DB_PATH = (ROOT_DIR / "tests" / "test_library_fulltext.db").resolve()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import ProjectModel, UserModel, UserRole  # noqa: E402
from app.platform import egress, library, library_fulltext as lf  # noqa: E402

PDF = b"%PDF-1.7\n1 0 obj\n<< >>\nendobj\n"
OA_URL = "https://repo.example.org/paper.pdf"


class Resp:
    def __init__(self, status=200, content=PDF, ctype="application/pdf", extra=None):
        self.status_code, self.content = status, content
        self.headers = {"content-type": ctype, **(extra or {})}


@pytest_asyncio.fixture
async def world():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as s:
        user = UserModel(email="autora@ejemplo.com", hashed_password=hash_password("Contrasena-1234"),
                         full_name="Autora", role=UserRole.REDACTOR, is_active=True)
        s.add(user)
        await s.commit()
        p1 = ProjectModel(name="P1", owner_id=user.id)
        s.add(p1)
        await s.commit()
        ids = {"p1": p1.id}
    yield ids
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def red(monkeypatch):
    """Dobles de egreso e índice; registra a quién se llamó."""
    estado = {"urls": [], "quien": [], "resp": Resp(), "indexados": 0, "indexa_ok": True}

    async def safe_get(url, *, quien="egress", **kw):
        estado["urls"].append(url)
        estado["quien"].append(quien)
        if isinstance(estado["resp"], Exception):
            raise estado["resp"]
        return estado["resp"]

    async def index_pdf(project, raw, filename, **kw):
        if not estado["indexa_ok"]:
            raise lf.FulltextError("índice caído")
        estado["indexados"] += 1
        return "doc-123", 4

    monkeypatch.setattr(egress, "safe_get", safe_get)
    monkeypatch.setattr(lf, "index_pdf", index_pdf)
    return estado


@pytest.fixture
def client():
    from app.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _headers(ac, project):
    r = await ac.post("/api/v1/auth/login", json={"email": "autora@ejemplo.com", "password": "Contrasena-1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}", "X-Project-Id": str(project)}


async def _candidato(project, oa=OA_URL, doi="10.1/abc"):
    async with AsyncSessionLocal() as s:
        doc = await library.add_document(
            s, project, title="Paper abierto", authors=["Ana Perez"], doi=doi, source_db="openalex",
            open_access_url=oa, curation_status="candidate", text_status="abstract_only")
        return str(doc.id)


async def _aceptar(ac, h, doc_id, **body):
    return await ac.post(f"/api/v1/agents/rag/library/records/{doc_id}/curation", headers=h,
                         json={"status": "accepted", **body})


@pytest.mark.asyncio
async def test_aceptar_con_url_abierta_descarga_por_safe_get_e_indexa(world, client, red):
    doc_id = await _candidato(world["p1"])
    async with client as ac:
        h = await _headers(ac, world["p1"])
        r = await _aceptar(ac, h, doc_id)
    j = r.json()
    assert r.status_code == 200, r.text
    assert j["curation_status"] == "accepted" and j["text_status"] == "full_text"
    assert j["doc_id"] == "doc-123" and j["fulltext"] == "full_text"
    assert red["urls"] == [OA_URL] and red["quien"] == ["literature_discovery"]
    assert red["indexados"] == 1


@pytest.mark.asyncio
async def test_sin_url_de_acceso_abierto_se_acepta_como_solo_resumen_sin_descargar(world, client, red):
    doc_id = await _candidato(world["p1"], oa=None)
    async with client as ac:
        h = await _headers(ac, world["p1"])
        j = (await _aceptar(ac, h, doc_id)).json()
    assert j["curation_status"] == "accepted" and j["text_status"] == "abstract_only"
    assert j["fulltext"] == "no_open_access_url"
    assert red["urls"] == []  # nunca se busca otra URL (ni doi.org ni la del registro)


@pytest.mark.parametrize("resp", [
    Resp(404, b""),
    Resp(200, b"<html>paywall</html>", ctype="text/html"),
    Resp(200, b"<html>paywall</html>", ctype="application/pdf"),   # miente: no hay magic bytes
    Resp(200, PDF, extra={"content-length": str(50 * 1024 * 1024)}),
    Resp(200, PDF + b"0" * (lf.MAX_PDF_BYTES + 1)),
    ConnectionError("sin red"),
    PermissionError("destino bloqueado por egress"),
])
@pytest.mark.asyncio
async def test_descarga_invalida_o_fallida_acepta_igualmente_como_solo_resumen(world, client, red, resp):
    red["resp"] = resp
    doc_id = await _candidato(world["p1"])
    async with client as ac:
        h = await _headers(ac, world["p1"])
        r = await _aceptar(ac, h, doc_id)
    j = r.json()
    assert r.status_code == 200, r.text
    assert j["curation_status"] == "accepted" and j["text_status"] == "abstract_only"
    assert j["fulltext"] == "download_failed" and j["fulltext_detail"]
    assert red["indexados"] == 0


@pytest.mark.asyncio
async def test_falla_del_indice_no_rompe_la_aceptacion(world, client, red):
    red["indexa_ok"] = False
    doc_id = await _candidato(world["p1"])
    async with client as ac:
        h = await _headers(ac, world["p1"])
        j = (await _aceptar(ac, h, doc_id)).json()
    assert j["curation_status"] == "accepted" and j["text_status"] == "abstract_only"


@pytest.mark.asyncio
async def test_marcar_imprescindible_no_vuelve_a_descargar(world, client, red):
    red["resp"] = Resp(500, b"")
    doc_id = await _candidato(world["p1"])
    async with client as ac:
        h = await _headers(ac, world["p1"])
        await _aceptar(ac, h, doc_id)
        await _aceptar(ac, h, doc_id, must_cite=True)
    assert len(red["urls"]) == 1


@pytest.mark.asyncio
async def test_descartar_no_descarga(world, client, red):
    doc_id = await _candidato(world["p1"])
    async with client as ac:
        h = await _headers(ac, world["p1"])
        r = await ac.post(f"/api/v1/agents/rag/library/records/{doc_id}/curation", headers=h,
                          json={"status": "discarded"})
        assert r.json()["curation_status"] == "discarded"
        r = await ac.post(f"/api/v1/agents/rag/library/records/{doc_id}/curation", headers=h,
                          json={"status": "otro"})
        assert r.status_code == 422
    assert red["urls"] == []


@pytest.mark.asyncio
async def test_subir_el_pdf_despues_pasa_la_ficha_a_full_text(world, client, red, monkeypatch):
    import app.routers.agents as agents

    async def ok(*a, **k):
        return True

    async def upsert(*a, **k):
        return 3

    monkeypatch.setattr(agents, "ensure_collection", ok)
    monkeypatch.setattr(agents, "upsert_chunks", upsert)
    monkeypatch.setattr(agents, "extract_doc_metadata", lambda *a, **k: {"title": "x", "authors": ""})
    doc_id = await _candidato(world["p1"], oa=None)
    async with client as ac:
        h = await _headers(ac, world["p1"])
        await _aceptar(ac, h, doc_id)
        r = await ac.post("/api/v1/agents/rag/library/upload", headers=h, data={"document_id": doc_id},
                          files={"file": ("p.txt", io.BytesIO(b"texto del paper"), "text/plain")})
        assert r.status_code == 200, r.text
        ficha = r.json()["library_document"]
        assert ficha["id"] == doc_id and ficha["text_status"] == "full_text"
        assert ficha["doi"] == "10.1/abc"
        lista = (await ac.get("/api/v1/agents/rag/library/records", headers=h)).json()["documents"]
        assert len(lista) == 1  # no crea una ficha duplicada
        r = await ac.post("/api/v1/agents/rag/library/upload", headers=h,
                          data={"document_id": "00000000-0000-0000-0000-000000000000"},
                          files={"file": ("p.txt", io.BytesIO(b"texto"), "text/plain")})
        assert r.status_code == 404


def test_la_descarga_solo_usa_la_puerta_de_egreso():
    fuente = Path(lf.__file__).read_text(encoding="utf-8")
    assert "httpx" not in fuente and "verify=False" not in fuente
    assert "egress.safe_get" in fuente and 'QUIEN = "literature_discovery"' in fuente
