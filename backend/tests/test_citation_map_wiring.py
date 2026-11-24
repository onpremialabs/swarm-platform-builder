"""SPEC-035 AC1/AC9 / T23.8 — el mapa de citas se guarda en la ejecución real.

Integración sobre BD real (SQLite de los tests): Redactor (citas extraídas con el mismo
código) -> Formateador (real, con un LLM falso) -> Publicador (real). El mapa debe quedar
versionado con la huella del TEXTO FINAL, la que lee la compuerta.
"""
from dataclasses import replace

import pytest
from sqlalchemy import select

from test_project_isolation import _proyecto, _usuario, db  # noqa: F401  (fixtures y ayudas)
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models import ArticleModel, ArticleStatus, PublicationGateReportModel, UserRole
from app.models.citation_link import CitationLinkModel
from app.modules.agents.adapters import formateador, publicador
from app.modules.agents.domain import alejandria
from app.platform import citations
from app.platform.publication_gate import gate as gate_module
from app.platform.publication_gate.service import text_sha256
from app.platform.publication_gate.types import CriterionResult, CriterionStatus

EXTRACTO = "La metformina reduce la glucosa en sangre en pacientes con diabetes tipo 2."
RESULTADOS = [{"doc_id": "doc-1", "chunk_index": 0, "filename": "met.pdf", "page": 7, "text": EXTRACTO}]
BORRADOR = """## Introducción
La metformina reduce la glucosa en sangre en pacientes con diabetes tipo 2 [F1].

## Metodología
Texto.

## Resultados
Texto.

## Discusión
Texto.

## Referencias
Lista.
"""
FUENTE = {"title": "Deep learning", "authors": "LeCun, Bengio, Hinton", "year": "2015",
          "journal": "Nature", "doi": "10.1038/nature14539"}


@pytest.fixture(autouse=True)
def _juez_de_citas_simulado(monkeypatch):
    """La plantilla declara el juez (T23.4): sin proveedor real, responde `supported`."""
    async def juez(prompt, **kw):
        return '{"verdict": "supported", "rationale": "el fragmento lo respalda"}'
    monkeypatch.setattr("app.platform.llm.call_llm", juez)


@pytest.fixture(autouse=True)
def _referencias_resueltas(monkeypatch):
    async def ok(sources, cfg, **kw):
        return CriterionResult("reference_existence", CriterionStatus.PASSED, []), list(sources)

    monkeypatch.setattr(gate_module, "check_reference_existence", ok)


@pytest.fixture(autouse=True)
def _restaura_llm():
    original = formateador.call_llm
    yield
    formateador.call_llm = original


async def _articulo():
    autora = await _usuario("autora@ejemplo.com", UserRole.REDACTOR)
    proyecto = await _proyecto("P", owner_id=autora.id)
    async with AsyncSessionLocal() as s:
        art = ArticleModel(title="T", body="", author_id=autora.id, project_id=proyecto.id,
                           status=ArticleStatus.DRAFT)
        s.add(art)
        await s.commit()
        await s.refresh(art)
    return art


def _estado_del_redactor(art, borrador=BORRADOR):
    """Lo que deja el Redactor en el estado (mismo código que `adapters/redactor.py`)."""
    mapa = citations.assign_cite_ids(RESULTADOS)
    leidas = citations.extract_citations(borrador, mapa)
    return {"article_id": art.id, "draft_text": borrador, "sources": [FUENTE],
            "citation_map": mapa, "citations": leidas["citations"]}


async def _ejecutar(art, *, formatear, borrador=BORRADOR, estado=None):
    estado = dict(estado or _estado_del_redactor(art, borrador))
    if formatear:
        async def llm(prompt, **kw):
            # Un Formateador que SÍ reescribe el texto.
            return borrador.replace("[F1]", "[F1] (Autor, 2020)").replace("Texto.", "Texto reescrito.")
        formateador.call_llm = llm
        estado.update(await formateador.run_formateador(estado))
    return estado, await publicador.run_publicador(estado)


async def _mapa_vigente(art_id):
    async with AsyncSessionLocal() as s:
        art = await s.get(ArticleModel, art_id)
        return art, await citations.current_citation_map(s, art)


async def _informe(art_id):
    async with AsyncSessionLocal() as s:
        filas = (await s.execute(select(PublicationGateReportModel).where(
            PublicationGateReportModel.article_id == art_id))).scalars().all()
    return filas[-1]


def _criterio(informe):
    return next((c for c in informe.criteria["criteria"] if c["criterion"] == "citation_support"), None)


@pytest.mark.asyncio
@pytest.mark.parametrize("formatear", [False, True], ids=["sin_formateador", "formateador_reescribe"])
async def test_current_citation_map_devuelve_filas_tras_una_ejecucion_completa(db, formatear):
    art = await _articulo()
    estado, res = await _ejecutar(art, formatear=formatear)
    if formatear:
        assert estado["formatted_text"] != BORRADOR  # el texto final NO es la salida del Redactor
    a, mapa = await _mapa_vigente(art.id)
    assert len(mapa) == 1
    fila = mapa[0]
    assert fila.text_sha256 == text_sha256(a.body)
    assert (fila.citation_key, fila.doc_id, fila.page, fila.excerpt) == ("F1", "doc-1", 7, EXTRACTO)
    assert fila.claim and "[F1]" not in fila.claim
    assert fila.excerpt_sha256 and fila.status == "supported"  # lo fijó el juez (T23.4)
    # La compuerta evaluó con ese mapa y no lo tomó por «sin mapa».
    crit = _criterio(await _informe(art.id))
    assert crit is not None and crit["status"] == "passed"


@pytest.mark.asyncio
async def test_no_se_guarda_el_mapa_con_la_huella_de_la_salida_del_redactor(db):
    art = await _articulo()
    await _ejecutar(art, formatear=True)
    async with AsyncSessionLocal() as s:
        huellas = {f.text_sha256 for f in (await s.execute(select(CitationLinkModel))).scalars()}
    assert huellas == {text_sha256((await _mapa_vigente(art.id))[0].body)}
    assert text_sha256(BORRADOR) not in huellas


@pytest.mark.asyncio
async def test_reejecutar_es_idempotente_por_huella(db):
    art = await _articulo()
    estado, _ = await _ejecutar(art, formatear=True)
    await publicador.run_publicador(estado)
    _, mapa = await _mapa_vigente(art.id)
    assert len(mapa) == 1


@pytest.mark.asyncio
async def test_texto_sin_citas_queda_not_verified_y_lo_dice_sin_bloquear_en_modo_aviso(db):
    art = await _articulo()
    logs = []
    estado = _estado_del_redactor(art, BORRADOR.replace(" [F1]", ""))
    estado["_log"] = lambda m, lvl="info": logs.append((lvl, m))
    _, res = await _ejecutar(art, formatear=False, estado=estado)
    crit = _criterio(await _informe(art.id))
    assert crit["status"] == "not_verified" and crit["advisory"] is True
    assert crit["evidence"] == [{"problem": "no_citations"}]
    assert res["gate_failed"] is False  # modo aviso: no bloquea
    a, _ = await _mapa_vigente(art.id)
    assert a.status == ArticleStatus.IN_REVIEW
    assert any(lvl == "warning" and "citation_support" in m for lvl, m in logs)  # y lo dice


@pytest.mark.asyncio
async def test_con_enforce_encendido_el_mismo_caso_bloquea(db, monkeypatch):
    monkeypatch.setattr(settings, "CITATION_SUPPORT_ENFORCE", True)
    art = await _articulo()
    _, res = await _ejecutar(art, formatear=False, borrador=BORRADOR.replace(" [F1]", ""))
    assert res["gate_failed"] is True
    assert [b["criterion"] for b in res["gate_blockers"]] == ["citation_support"]
    assert (await _informe(art.id)).criteria["passed"] is False


@pytest.mark.asyncio
async def test_si_el_mapa_no_se_pudo_guardar_queda_not_verified_y_no_se_omite(db, monkeypatch):
    async def roto(*a, **k):
        raise RuntimeError("disco lleno")

    monkeypatch.setattr(citations, "save_citation_map", roto)
    art = await _articulo()
    logs = []
    estado = _estado_del_redactor(art)
    estado["_log"] = lambda m, lvl="info": logs.append((lvl, m))
    _, res = await _ejecutar(art, formatear=False, estado=estado)
    crit = _criterio(await _informe(art.id))
    assert crit["status"] == "not_verified" and crit["evidence"] == [{"problem": "map_unavailable"}]
    assert res["gate_failed"] is False  # aviso
    assert any(lvl == "warning" and "mapa de citas" in m for lvl, m in logs)


@pytest.mark.asyncio
async def test_sin_gate_citation_support_declarado_se_comporta_como_antes(db, monkeypatch):
    pkg = alejandria.package()
    sin_soporte = replace(pkg, gate=replace(pkg.gate, citation_support_min_overlap=None))
    monkeypatch.setattr(alejandria, "package", lambda: sin_soporte)
    art = await _articulo()
    _, res = await _ejecutar(art, formatear=True)
    assert _criterio(await _informe(art.id)) is None
    _, mapa = await _mapa_vigente(art.id)
    assert mapa == []  # no se guarda nada
    assert res["gate_failed"] is False


def test_la_plantilla_de_alejandria_declara_el_criterio_y_el_interruptor_esta_apagado():
    assert alejandria.package().gate.citation_support_min_overlap == 0.25
    from app.core.config import Settings
    assert Settings.model_fields["CITATION_SUPPORT_ENFORCE"].default is False


def test_documents_page_lee_doc_y_page_de_la_url_y_los_textos_estan_en_los_catalogos():
    """El enlace de la pestaña Fuentes apunta a `?doc=&page=`; la página debe leerlos."""
    import json
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2] / "frontend" / "src" / "platform"
    codigo = (raiz / "pages" / "DocumentsPage.jsx").read_text(encoding="utf-8")
    assert "useSearchParams" in codigo and "params.get('doc')" in codigo and "params.get('page')" in codigo
    for idioma in ("es", "en"):
        docs = json.loads((raiz / "i18n" / f"{idioma}.json").read_text(encoding="utf-8"))["documents"]
        assert {"citedTarget", "citedTargetNoPage", "citedNotFound"} <= set(docs)
