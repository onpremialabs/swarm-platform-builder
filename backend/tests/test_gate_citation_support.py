"""Criterio de soporte de cada cita (SPEC-035 / T23.3 / AC2, AC4)."""
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest
import pytest_asyncio

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

TEST_DB_PATH = (ROOT_DIR / "tests" / "test_gate_citation_support.db").resolve()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import ArticleModel, ArticleStatus, UserModel, UserRole  # noqa: E402
from app.platform import citations  # noqa: E402
from app.platform.citations import CitationInput  # noqa: E402
from app.platform.publication_gate import CriterionStatus  # noqa: E402
from app.platform.publication_gate.citation_support import (  # noqa: E402
    check_citation_support, overlap,
)
from app.platform.publication_gate.config import GateConfig, GateConfigError, parse_gate  # noqa: E402
from app.platform.publication_gate.service import evaluate_and_store  # noqa: E402

EXTRACTO = "La dosis diaria de metformina redujo la glucosa en ayunas en adultos con diabetes."
CLAIM_OK = "La metformina redujo la glucosa en ayunas en adultos con diabetes"
CLAIM_LEJANO = "Las ballenas migran miles de kilometros cada invierno"
TEXTO = "Texto del manuscrito [F1]."


def _link(**kw):
    base = {"citation_key": "F1", "claim_index": 0, "claim": CLAIM_OK, "doc_id": "d1",
            "excerpt": EXTRACTO, "confirmed_at": None}
    base.update(kw)
    return base


def test_overlap_es_determinista_y_sin_acentos():
    assert overlap(CLAIM_OK, EXTRACTO) > 0.8
    assert overlap(CLAIM_LEJANO, EXTRACTO) == 0.0
    assert overlap("el la de", EXTRACTO) is None


def test_cita_con_solape_alto_no_tiene_nada_que_objetar():
    r = check_citation_support(TEXTO, [_link()], 0.25)
    assert r.status is CriterionStatus.PASSED and not r.blocking


def test_ac2_cita_sin_fragmento_es_not_verified_y_bloquea():
    for roto in ({"doc_id": None}, {"excerpt": ""}, {"excerpt": "   "}):
        r = check_citation_support(TEXTO, [_link(**roto)])
        assert r.status is CriterionStatus.NOT_VERIFIED and r.blocking
        assert r.evidence[0]["reason"] == "no_fragment"


def test_ac2_la_confirmacion_manual_no_rescata_una_cita_sin_fragmento():
    r = check_citation_support(TEXTO, [_link(doc_id=None, confirmed_at=datetime.utcnow())])
    assert r.blocking and r.evidence[0]["reason"] == "no_fragment"


def test_ac4_solape_bajo_marca_revision_humana_sin_juez():
    r = check_citation_support(TEXTO, [_link(claim=CLAIM_LEJANO)], 0.25)
    assert r.status is CriterionStatus.NOT_VERIFIED and r.blocking
    e = r.evidence[0]
    assert e["reason"] == "low_overlap" and e["needs_human_review"] is True
    assert e["overlap"] < e["min_overlap"] == 0.25


def test_ac4_umbral_configurable():
    parcial = _link(claim="La metformina redujo la glucosa y ademas mejoro el sueno profundo nocturno")
    assert check_citation_support(TEXTO, [parcial], 0.2).status is CriterionStatus.PASSED
    assert check_citation_support(TEXTO, [parcial], 0.9).blocking


def test_ac4_confirmada_por_el_autor_deja_de_bloquear():
    r = check_citation_support(TEXTO, [_link(claim=CLAIM_LEJANO, confirmed_at=datetime.utcnow())])
    assert r.status is CriterionStatus.PASSED


def test_falla_cerrada_sin_mapa_sin_citas_o_marcador_huerfano():
    assert check_citation_support(TEXTO, None).evidence[0]["problem"] == "map_unavailable"
    assert check_citation_support("Sin marcadores.", []).evidence[0]["problem"] == "no_citations"
    r = check_citation_support("Dato [F1]. Otro [F2, F3].", [_link()])
    assert r.blocking
    assert [e["citation_key"] for e in r.evidence] == ["F2", "F3"]
    assert all(e["reason"] == "unmapped" for e in r.evidence)


def test_afirmacion_sin_palabras_con_contenido_no_se_aprueba():
    r = check_citation_support(TEXTO, [_link(claim="Si.")])
    assert r.blocking and r.evidence[0]["reason"] == "no_claim"


def test_config_declara_el_criterio_y_valida_el_umbral():
    assert GateConfig().citation_support_min_overlap is None
    assert parse_gate({}).citation_support_min_overlap is None
    assert parse_gate({"citation_support": {}}).citation_support_min_overlap == 0.25
    assert parse_gate({"citation_support": {"min_overlap": 0.4}}).citation_support_min_overlap == 0.4
    for malo in ({"min_overlap": 1.5}, {"min_overlap": "x"}, {"otro": 1}, [1]):
        with pytest.raises(GateConfigError):
            parse_gate({"citation_support": malo})


@pytest_asyncio.fixture
async def article():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as s:
        user = UserModel(email="a@ejemplo.com", hashed_password=hash_password("x" * 12),
                         full_name="A", role=UserRole.REDACTOR, is_active=True)
        s.add(user)
        await s.commit()
        art = ArticleModel(title="T", body=TEXTO, status=ArticleStatus.DRAFT, author_id=user.id)
        s.add(art)
        await s.commit()
        await s.refresh(art)
        yield art.id
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _criterio(row):
    return next(c for c in row.criteria["criteria"] if c["criterion"] == "citation_support")


@pytest.mark.asyncio
async def test_la_compuerta_lee_el_mapa_vigente_y_lo_incluye_en_el_informe(article):
    cfg = parse_gate({"citation_support": {"min_overlap": 0.25}})
    async with AsyncSessionLocal() as s:
        art = await s.get(ArticleModel, article)
        fuentes = [{"title": "X"}]
        row, _ = await evaluate_and_store(s, art, cfg, fuentes)
        assert _criterio(row)["status"] == "not_verified"  # sin mapa guardado: falla cerrada
        await citations.save_citation_map(s, art.id, art.body, [
            CitationInput("F1", CLAIM_OK, doc_id="d1", excerpt=EXTRACTO)])
        row, report = await evaluate_and_store(s, art, cfg, fuentes)
        assert _criterio(row)["status"] == "passed"
        await citations.save_citation_map(s, art.id, art.body, [CitationInput("F1", CLAIM_OK)])
        row, report = await evaluate_and_store(s, art, cfg, fuentes)
        assert _criterio(row)["status"] == "not_verified"
        assert any(c.criterion == "citation_support" for c in report.blockers)


@pytest.mark.asyncio
async def test_sin_declarar_el_criterio_la_compuerta_no_cambia(article):
    async with AsyncSessionLocal() as s:
        art = await s.get(ArticleModel, article)
        row, _ = await evaluate_and_store(s, art, GateConfig(), [{"title": "X"}])
    assert all(c["criterion"] != "citation_support" for c in row.criteria["criteria"])
