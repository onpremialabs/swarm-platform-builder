"""SPEC-035 AC6 / T23.6 — lectura del mapa de citas y confirmación manual por API."""
import pytest
from httpx import ASGITransport, AsyncClient

from test_project_isolation import (  # noqa: F401  (fixtures y ayudas de ese módulo)
    _cabeceras, _proyecto, _token, _usuario, client, db,
)
from app.core.database import AsyncSessionLocal
from app.models import ArticleModel, ArticleStatus, UserRole
from app.platform import citations
from app.platform.citations import CitationInput

CUERPO = "La dosis fue de 5 mg [F1]."


async def _articulo(con_mapa=True, cuerpo=CUERPO):
    autora = await _usuario("autora@ejemplo.com", UserRole.REDACTOR)
    proyecto = await _proyecto("P", owner_id=autora.id)
    async with AsyncSessionLocal() as s:
        art = ArticleModel(title="T", body=cuerpo, author_id=autora.id,
                           project_id=proyecto.id, status=ArticleStatus.DRAFT)
        s.add(art)
        await s.commit()
        await s.refresh(art)
        if con_mapa:
            await citations.save_citation_map(s, art.id, CUERPO, [
                CitationInput("F1", "La dosis fue de 5 mg.", doc_id="d1", page=3, excerpt="dosis de 5 mg"),
            ])
            await s.commit()
    return autora, proyecto, art


async def _llamar(usuario, proyecto, metodo, ruta, project_id=None):
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        token = await _token(ac, usuario.email)
        return await getattr(ac, metodo)(ruta, headers=_cabeceras(token, project_id or proyecto.id))


@pytest.mark.asyncio
async def test_lee_el_mapa_vigente(db, client):
    autora, proyecto, art = await _articulo()
    r = await _llamar(autora, proyecto, "get", f"/api/v1/articles/{art.id}/citations")
    assert r.status_code == 200, r.text
    (c,) = r.json()["citations"]
    assert (c["citation_key"], c["doc_id"], c["page"], c["status"]) == ("F1", "d1", 3, "not_verified")
    assert c["confirmed_at"] is None


@pytest.mark.asyncio
async def test_sin_mapa_guardado_la_lista_viene_vacia(db, client):
    autora, proyecto, art = await _articulo(con_mapa=False)
    r = await _llamar(autora, proyecto, "get", f"/api/v1/articles/{art.id}/citations")
    assert r.status_code == 200
    assert r.json() == {"citations": []}


@pytest.mark.asyncio
async def test_confirmar_registra_quien_y_cuando_sin_tocar_el_estado(db, client):
    autora, proyecto, art = await _articulo()
    lista = (await _llamar(autora, proyecto, "get", f"/api/v1/articles/{art.id}/citations")).json()
    link = lista["citations"][0]["id"]
    r = await _llamar(autora, proyecto, "post", f"/api/v1/articles/{art.id}/citations/{link}/confirm")
    assert r.status_code == 200, r.text
    assert r.json()["confirmed_by"] == str(autora.id)
    assert r.json()["confirmed_at"]
    assert r.json()["status"] == "not_verified"


@pytest.mark.asyncio
async def test_una_cita_de_otro_texto_o_inexistente_da_404(db, client):
    from uuid import uuid4

    autora, proyecto, art = await _articulo()
    r = await _llamar(autora, proyecto, "post", f"/api/v1/articles/{art.id}/citations/{uuid4()}/confirm")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_sin_cabecera_de_proyecto_no_se_adivina(db, client):
    autora, proyecto, art = await _articulo()
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        token = await _token(ac, autora.email)
        r = await ac.get(f"/api/v1/articles/{art.id}/citations", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_otro_proyecto_no_ve_ni_confirma(db, client):
    autora, proyecto, art = await _articulo()
    otro = await _proyecto("Q", owner_id=autora.id)
    r = await _llamar(autora, proyecto, "get", f"/api/v1/articles/{art.id}/citations", project_id=otro.id)
    assert r.status_code == 404
    link = (await _llamar(autora, proyecto, "get", f"/api/v1/articles/{art.id}/citations")).json()["citations"][0]["id"]
    r = await _llamar(autora, proyecto, "post",
                      f"/api/v1/articles/{art.id}/citations/{link}/confirm", project_id=otro.id)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_un_tercero_no_lee_ni_confirma(db, client):
    autora, proyecto, art = await _articulo()
    intruso = await _usuario("intruso@ejemplo.com", UserRole.REDACTOR)
    r = await _llamar(intruso, proyecto, "get", f"/api/v1/articles/{art.id}/citations")
    assert r.status_code in (403, 404)
    link = (await _llamar(autora, proyecto, "get", f"/api/v1/articles/{art.id}/citations")).json()["citations"][0]["id"]
    r = await _llamar(intruso, proyecto, "post", f"/api/v1/articles/{art.id}/citations/{link}/confirm")
    assert r.status_code in (403, 404)


@pytest.mark.asyncio
async def test_un_lector_no_confirma(db, client):
    autora, proyecto, art = await _articulo()
    lector = await _usuario("lector@ejemplo.com", UserRole.LECTOR)
    link = (await _llamar(autora, proyecto, "get", f"/api/v1/articles/{art.id}/citations")).json()["citations"][0]["id"]
    r = await _llamar(lector, proyecto, "post", f"/api/v1/articles/{art.id}/citations/{link}/confirm")
    assert r.status_code in (403, 404)


@pytest.mark.asyncio
async def test_el_revisor_asignado_lee_pero_no_confirma(db, client):
    autora, proyecto, art = await _articulo()
    revisor = await _usuario("revisor@ejemplo.com", UserRole.REDACTOR)
    async with AsyncSessionLocal() as s:
        a = await s.get(ArticleModel, art.id)
        a.reviewer_id = revisor.id
        await s.commit()
    from app.models import UserProjectAccessModel
    async with AsyncSessionLocal() as s:
        s.add(UserProjectAccessModel(user_id=revisor.id, project_id=proyecto.id))
        await s.commit()
    r = await _llamar(revisor, proyecto, "get", f"/api/v1/articles/{art.id}/citations")
    assert r.status_code == 200, r.text
    link = r.json()["citations"][0]["id"]
    r = await _llamar(revisor, proyecto, "post", f"/api/v1/articles/{art.id}/citations/{link}/confirm")
    assert r.status_code == 403
