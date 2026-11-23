"""Mapa cita -> fragmento versionado con el texto (SPEC-035 / T23.2 / AC1, AC6)."""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

TEST_DB_PATH = (ROOT_DIR / "tests" / "test_citation_links.db").resolve()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    ArticleModel, ArticleStatus, CitationLinkModel, UserModel, UserRole,
)
from app.platform import citations, retention  # noqa: E402
from app.platform.citations import CitationInput  # noqa: E402
from app.platform.publication_gate.service import text_sha256  # noqa: E402


@pytest_asyncio.fixture
async def world():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as s:
        user = UserModel(
            email="autora@ejemplo.com", hashed_password=hash_password("x" * 12),
            full_name="Autora", role=UserRole.REDACTOR, is_active=True,
        )
        s.add(user)
        await s.commit()
        art = ArticleModel(title="A", body="Texto v1", status=ArticleStatus.DRAFT,
                           author_id=user.id)
        s.add(art)
        await s.commit()
        await s.refresh(user)
        await s.refresh(art)
        ids = {"user": user.id, "article": art.id}
    yield ids
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _cites():
    return [
        CitationInput("d1:p3", "La dosis fue de 5 mg.", doc_id="d1", page=3, excerpt="dosis de 5 mg"),
        CitationInput("d9:p1", "Sin fragmento."),
    ]


@pytest.mark.asyncio
async def test_saves_map_with_doc_page_excerpt_and_hash(world):
    async with AsyncSessionLocal() as s:
        await citations.save_citation_map(s, world["article"], "Texto v1", _cites())
        await s.commit()
        rows = await citations.get_citation_map(s, world["article"], text_sha256("Texto v1"))
    assert [r.citation_key for r in rows] == ["d1:p3", "d9:p1"]
    a, b = rows
    assert (a.doc_id, a.page, a.excerpt) == ("d1", 3, "dosis de 5 mg")
    assert a.excerpt_sha256 == citations.excerpt_sha256("dosis de 5 mg")
    assert a.text_sha256 == text_sha256("Texto v1")
    # Falla cerrada: nada nace verificado, y una cita sin fragmento tampoco.
    assert a.status == b.status == "not_verified"
    assert b.doc_id is None


@pytest.mark.asyncio
async def test_new_text_version_keeps_the_previous_map(world):
    async with AsyncSessionLocal() as s:
        await citations.save_citation_map(s, world["article"], "v1", _cites())
        await citations.save_citation_map(s, world["article"], "v2", _cites()[:1])
        await s.commit()
        v1 = await citations.get_citation_map(s, world["article"], text_sha256("v1"))
        v2 = await citations.get_citation_map(s, world["article"], text_sha256("v2"))
    assert (len(v1), len(v2)) == (2, 1)


@pytest.mark.asyncio
async def test_resaving_same_text_is_idempotent_and_keeps_confirmations(world):
    async with AsyncSessionLocal() as s:
        rows = await citations.save_citation_map(s, world["article"], "v1", _cites())
        await s.commit()
        await citations.confirm_citation(s, rows[0].id, world["user"])
        await s.commit()
        await citations.save_citation_map(s, world["article"], "v1", _cites())
        await s.commit()
        total = await s.scalar(select(func.count()).select_from(CitationLinkModel))
        rows = await citations.get_citation_map(s, world["article"], text_sha256("v1"))
    assert total == 2
    assert rows[0].confirmed_by == world["user"] and rows[0].confirmed_at is not None
    assert rows[1].confirmed_at is None


@pytest.mark.asyncio
async def test_changed_excerpt_drops_the_confirmation(world):
    async with AsyncSessionLocal() as s:
        rows = await citations.save_citation_map(s, world["article"], "v1", _cites())
        await citations.confirm_citation(s, rows[0].id, world["user"])
        await s.commit()
        cambiada = _cites()
        cambiada[0].excerpt = "otro pasaje"
        rows = await citations.save_citation_map(s, world["article"], "v1", cambiada)
        await s.commit()
    assert rows[0].confirmed_at is None


@pytest.mark.asyncio
async def test_confirm_records_who_and_when_without_touching_status(world):
    antes = datetime.utcnow()
    async with AsyncSessionLocal() as s:
        rows = await citations.save_citation_map(s, world["article"], "v1", _cites())
        await s.commit()
        link = await citations.confirm_citation(s, rows[0].id, world["user"])
        await s.commit()
    assert link.confirmed_by == world["user"]
    assert link.confirmed_at >= antes
    assert link.status == "not_verified"


@pytest.mark.asyncio
async def test_confirm_unknown_citation_returns_none(world):
    async with AsyncSessionLocal() as s:
        assert await citations.confirm_citation(s, uuid4(), world["user"]) is None


@pytest.mark.asyncio
async def test_current_map_is_the_one_for_the_current_body(world):
    async with AsyncSessionLocal() as s:
        art = await s.get(ArticleModel, world["article"])
        await citations.save_citation_map(s, art.id, art.body, _cites())
        await s.commit()
        assert len(await citations.current_citation_map(s, art)) == 2
        art.body = "texto editado"
        assert await citations.current_citation_map(s, art) == []


@pytest.mark.asyncio
async def test_status_check_constraint_rejects_invalid_values(world):
    async with AsyncSessionLocal() as s:
        s.add(CitationLinkModel(
            article_id=world["article"], text_sha256="x" * 64, citation_key="k",
            claim_index=0, status="verified-ish",
        ))
        with pytest.raises(IntegrityError):
            await s.commit()


def test_article_fk_declares_cascade():
    fk = next(iter(CitationLinkModel.__table__.c.article_id.foreign_keys))
    assert fk.ondelete == "CASCADE"


@pytest.mark.asyncio
async def test_retention_purges_old_drafts_but_not_published(world):
    vieja = datetime.utcnow() - timedelta(days=400)
    async with AsyncSessionLocal() as s:
        pub = ArticleModel(title="P", body="b", status=ArticleStatus.PUBLISHED,
                           author_id=world["user"])
        s.add(pub)
        await s.commit()
        for art_id in (world["article"], pub.id):
            for fila in await citations.save_citation_map(s, art_id, "v", _cites()[:1]):
                fila.created_at = vieja
        await s.commit()
        res = await retention.purge(s, apply=True)
        restantes = (await s.execute(select(CitationLinkModel.article_id))).scalars().all()
    assert res.counts["citation_links"] == 1
    assert restantes == [pub.id]
