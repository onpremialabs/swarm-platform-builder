"""Fuentes aportadas por el autor (SPEC-034 / T22.13 / AC4, AC5, AC7, AC14 / ADR-0013).

Sin red: el RAG y el LLM son dobles; la biblioteca es la real (SQLite).
"""
import pytest

from test_investigador_verified_only import (  # noqa: F401  (fixtures y ayudas)
    AsyncSessionLocal, _doc, _estado, _hit, entorno, investigador, library, mundo,
)
from test_library_curation_import import _headers, client, egreso, world  # noqa: F401


async def _declara(project, doc, user):
    async with AsyncSessionLocal() as s:
        return await library.declare_author_provided(s, project, doc.id, declared_by=user)


# ── AC14: la declaración ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_declarar_registra_quien_y_cuando_y_hace_citable(mundo):
    p, u = mundo["p1"], mundo["user"]
    doc = await _doc(p, 1, verified=None, doi=False)
    async with AsyncSessionLocal() as s:
        assert library.is_citable(await library.get_document(s, p, doc.id)) is False
    hecho = await _declara(p, doc, u)
    assert hecho.author_provided and hecho.author_provided_by == u and hecho.author_provided_at
    assert library.source_class(hecho) == library.CLASS_AUTHOR_PROVIDED
    assert library.is_citable(hecho)


@pytest.mark.asyncio
async def test_la_declaracion_es_reversible(mundo):
    p = mundo["p1"]
    doc = await _doc(p, 1, verified=None, doi=False)
    await _declara(p, doc, mundo["user"])
    async with AsyncSessionLocal() as s:
        rev = await library.revoke_author_provided(s, p, doc.id)
    assert not rev.author_provided and rev.author_provided_by is None
    assert library.source_class(rev) is None and not library.is_citable(rev)


@pytest.mark.asyncio
async def test_solo_una_persona_puede_declarar(mundo):
    p = mundo["p1"]
    doc = await _doc(p, 1, verified=None, doi=False)
    with pytest.raises(ValueError, match="persona"):
        await _declara(p, doc, None)


@pytest.mark.asyncio
async def test_un_doi_declarado_no_se_lava_con_la_declaracion(mundo):
    p = mundo["p1"]
    doc = await _doc(p, 1, verified=None, doi=True)       # DOI declarado, sin resolver
    with pytest.raises(ValueError, match="DOI"):
        await _declara(p, doc, mundo["user"])


@pytest.mark.asyncio
async def test_solo_un_documento_aceptado_puede_declararse(mundo):
    p = mundo["p1"]
    doc = await _doc(p, 1, verified=None, doi=False, curation="candidate")
    with pytest.raises(ValueError, match="aceptado"):
        await _declara(p, doc, mundo["user"])


@pytest.mark.asyncio
async def test_aportar_un_doi_verificado_sustituye_a_la_declaracion(mundo):
    p, u = mundo["p1"], mundo["user"]
    doc = await _doc(p, 1, verified=None, doi=False)
    await _declara(p, doc, u)
    async with AsyncSessionLocal() as s:
        v = await library.mark_verified(
            s, p, doc.id, "author_supplied", verified_by=u, doi="10.1000/nuevo")
    assert not v.author_provided and library.source_class(v) == library.CLASS_IDENTIFIED


@pytest.mark.asyncio
async def test_la_declaracion_no_cruza_proyectos(mundo):
    doc = await _doc(mundo["p1"], 1, verified=None, doi=False)
    async with AsyncSessionLocal() as s:
        assert await library.declare_author_provided(
            s, mundo["p2"], doc.id, declared_by=mundo["user"]) is None


# ── AC5 / AC7 / AC14: el Investigador ───────────────────────────────────────

@pytest.mark.asyncio
async def test_investigador_cita_las_dos_clases_con_su_etiqueta(mundo, entorno):
    p, u = mundo["p1"], mundo["user"]
    await _doc(p, 1)
    await _doc(p, 2)
    propio = await _doc(p, 3, verified=None, doi=False)
    await _declara(p, propio, u)
    entorno["resultados"]["hits"] = [_hit(n) for n in (1, 2, 3)]
    out = await investigador.run_investigador(_estado(p))
    assert not out.get("abstained")
    clases = {s["doc_id"]: s["source_class"] for s in out["sources"]}
    assert clases == {"rag-1": "identified", "rag-2": "identified", "rag-3": "author_provided"}
    propia = next(s for s in out["sources"] if s["doc_id"] == "rag-3")
    assert propia["doi"] is None and propia["author_provided_at"]
    assert "aportado por el autor" in out["research_data"]


@pytest.mark.asyncio
async def test_sin_declarar_sigue_siendo_solo_contexto(mundo, entorno):
    p = mundo["p1"]
    await _doc(p, 1)
    await _doc(p, 2)
    await _doc(p, 3, verified=None, doi=False)             # aceptado, sin DOI, sin declarar
    entorno["resultados"]["hits"] = [_hit(n) for n in (1, 2, 3)]
    out = await investigador.run_investigador(_estado(p))
    assert out["abstained"] is True and out["abstention"]["citable_sources"] == 2
    assert "declár" in out["abstention"]["message"] and "aportado por el autor" in out["abstention"]["message"]


@pytest.mark.asyncio
async def test_no_se_abstiene_por_falta_de_doi_si_hay_n_citables(mundo, entorno):
    """Ninguna fuente tiene DOI y aun así hay N=3 citables: no hay abstención."""
    p, u = mundo["p1"], mundo["user"]
    for n in (1, 2, 3):
        d = await _doc(p, n, verified=None, doi=False)
        await _declara(p, d, u)
    entorno["resultados"]["hits"] = [_hit(n) for n in (1, 2, 3)]
    out = await investigador.run_investigador(_estado(p))
    assert not out.get("abstained") and len(out["sources"]) == 3


@pytest.mark.asyncio
async def test_se_abstiene_con_menos_de_n_citables_aunque_haya_declarados(mundo, entorno):
    p, u = mundo["p1"], mundo["user"]
    await _doc(p, 1)
    d = await _doc(p, 2, verified=None, doi=False)
    await _declara(p, d, u)
    entorno["resultados"]["hits"] = [_hit(n) for n in (1, 2)]
    out = await investigador.run_investigador(_estado(p))
    assert out["abstained"] is True and out["abstention"]["min_sources"] == 3
    assert entorno["llm"] == []                    # nada desde conocimiento paramétrico


# ── API ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_endpoint_declara_y_revierte(world, client):
    p = world["p1"]
    async with AsyncSessionLocal() as s:
        doc = await library.add_document(s, p, title="Informe interno", authors=["Equipo"])
        await library.set_curation(s, p, doc.id, "accepted")
    async with client as ac:
        h = await _headers(ac, "autora@ejemplo.com", p)
        url = f"/api/v1/agents/rag/library/records/{doc.id}/author-provided"
        r = await ac.post(url, json={"declared": True}, headers=h)
        assert r.status_code == 200, r.text
        v = r.json()
        assert v["author_provided"] and v["source_class"] == "author_provided" and v["citable"]
        assert v["author_provided_by"] == str(world["user"]) and v["author_provided_at"]
        r = await ac.post(url, json={"declared": False}, headers=h)
        assert r.status_code == 200 and r.json()["citable"] is False
        # Un DOI declarado no se puede «lavar»: 409.
        r = await ac.patch(f"/api/v1/agents/rag/library/records/{doc.id}",
                           json={"doi": "10.1000/xyz"}, headers=h)
        assert r.status_code == 200
        r = await ac.post(url, json={"declared": True}, headers=h)
        assert r.status_code == 409
