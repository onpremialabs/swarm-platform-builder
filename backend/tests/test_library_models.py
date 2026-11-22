"""Modelos de biblioteca y registro de búsqueda (SPEC-034 / T22.3 / AC3, AC6)."""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

TEST_DB_PATH = (ROOT_DIR / "tests" / "test_library_models.db").resolve()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, inspect, select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    ArticleModel, ArticleStatus, LibraryDocumentModel, ProjectModel, SearchLogModel,
    UserModel, UserRole, normalize_doi,
)
from app.platform import library, retention  # noqa: E402


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
    """Un usuario y dos proyectos."""
    async with AsyncSessionLocal() as session:
        user = UserModel(
            email="autora@ejemplo.com", hashed_password=hash_password("x" * 12),
            full_name="Autora", role=UserRole.REDACTOR, is_active=True,
        )
        p1 = ProjectModel(name="P1")
        p2 = ProjectModel(name="P2")
        session.add_all([user, p1, p2])
        await session.commit()
        for obj in (user, p1, p2):
            await session.refresh(obj)
        return {"user": user.id, "p1": p1.id, "p2": p2.id}


def _doc(**over):
    base = dict(title="Un artículo", authors=["Ada Lovelace"], year=2020, journal="Nature",
                source_db="openalex", doi="10.1000/ABC")
    base.update(over)
    return base


# --------------------------------------------------------------------------- #
# Valores por defecto y enums
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_defaults_are_candidate_abstract_only_unverified(world):
    async with AsyncSessionLocal() as s:
        doc = await library.add_document(s, world["p1"], **_doc())
    assert doc.curation_status == "candidate"
    assert doc.text_status == "abstract_only"
    assert doc.must_cite is False and doc.verified is False
    assert doc.verified_at is None and doc.verification_method is None
    assert doc.created_at is not None


@pytest.mark.parametrize("field", ["source_db", "text_status", "curation_status", "verification_method"])
def test_invalid_enum_values_are_rejected_by_the_model(field):
    with pytest.raises(ValueError):
        LibraryDocumentModel(title="x", **{field: "nope"})


def test_every_source_db_of_the_spec_is_accepted():
    for src in ("openalex", "crossref", "semantic_scholar", "arxiv", "pubmed", "manual"):
        assert LibraryDocumentModel(title="x", source_db=src).source_db == src


@pytest.mark.asyncio
async def test_check_constraint_rejects_invalid_values_even_bypassing_the_orm(world):
    from sqlalchemy import text
    async with AsyncSessionLocal() as s:
        with pytest.raises(IntegrityError):
            await s.execute(text(
                "INSERT INTO library_documents (id, project_id, title, authors, source_db, "
                "text_status, curation_status, must_cite, verified, created_at, updated_at) "
                "VALUES ('a', 'b', 't', '[]', 'bogus', 'full_text', 'candidate', 0, 0, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ))


# --------------------------------------------------------------------------- #
# DOI: normalización y unicidad por proyecto
# --------------------------------------------------------------------------- #

def test_doi_is_normalized():
    assert normalize_doi(" https://doi.org/10.1000/ABC ") == "10.1000/abc"
    assert normalize_doi("DOI:10.1/X") == "10.1/x"
    assert normalize_doi("   ") is None and normalize_doi(None) is None
    assert LibraryDocumentModel(title="x", doi="10.1/ABC").doi == "10.1/abc"


@pytest.mark.asyncio
async def test_doi_is_unique_within_a_project_regardless_of_case_and_prefix(world):
    async with AsyncSessionLocal() as s:
        await library.add_document(s, world["p1"], **_doc(doi="10.1000/ABC"))
    async with AsyncSessionLocal() as s:
        with pytest.raises(library.DuplicateDocumentError):
            await library.add_document(s, world["p1"], **_doc(doi="https://doi.org/10.1000/abc"))


@pytest.mark.asyncio
async def test_unique_constraint_holds_in_the_database_not_only_in_the_helper(world):
    async with AsyncSessionLocal() as s:
        s.add(LibraryDocumentModel(project_id=world["p1"], **_doc()))
        s.add(LibraryDocumentModel(project_id=world["p1"], **_doc()))
        with pytest.raises(IntegrityError):
            await s.commit()


@pytest.mark.asyncio
async def test_same_doi_is_allowed_in_another_project(world):
    async with AsyncSessionLocal() as s:
        await library.add_document(s, world["p1"], **_doc())
        await library.add_document(s, world["p2"], **_doc())
        assert len(await library.list_documents(s, world["p1"])) == 1
        assert len(await library.list_documents(s, world["p2"])) == 1


@pytest.mark.asyncio
async def test_several_documents_without_doi_coexist(world):
    async with AsyncSessionLocal() as s:
        await library.add_document(s, world["p1"], **_doc(doi=None, title="A"))
        await library.add_document(s, world["p1"], **_doc(doi=None, title="B"))
        assert len(await library.list_documents(s, world["p1"])) == 2


# --------------------------------------------------------------------------- #
# Aislamiento por proyecto
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_documents_and_searches_do_not_cross_projects(world):
    async with AsyncSessionLocal() as s:
        doc = await library.add_document(s, world["p1"], **_doc())
        await library.record_search(s, world["p1"], query="q", sources=["openalex"])
        assert await library.get_document(s, world["p2"], doc.id) is None
        assert await library.set_curation(s, world["p2"], doc.id, "accepted") is None
        assert await library.list_documents(s, world["p2"]) == []
        assert await library.list_searches(s, world["p2"]) == []
        assert len(await library.list_searches(s, world["p1"])) == 1


# --------------------------------------------------------------------------- #
# Curación (AC3) y verificación (ADR-0011)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_accept_discard_and_must_cite(world):
    async with AsyncSessionLocal() as s:
        doc = await library.add_document(s, world["p1"], added_by=world["user"], **_doc())
        assert doc.added_by == world["user"]
        d = await library.set_curation(s, world["p1"], doc.id, "accepted", must_cite=True)
        assert (d.curation_status, d.must_cite) == ("accepted", True)
        d = await library.set_curation(s, world["p1"], doc.id, "discarded", must_cite=True)
        assert (d.curation_status, d.must_cite) == ("discarded", False)


@pytest.mark.asyncio
async def test_must_cite_requires_accepted_at_database_level(world):
    async with AsyncSessionLocal() as s:
        s.add(LibraryDocumentModel(project_id=world["p1"], must_cite=True, **_doc()))
        with pytest.raises(IntegrityError):
            await s.commit()


@pytest.mark.asyncio
async def test_only_accepted_and_verified_documents_are_citable(world):
    async with AsyncSessionLocal() as s:
        ok = await library.add_document(s, world["p1"], **_doc(doi="10.1/ok"))
        sin_verificar = await library.add_document(s, world["p1"], **_doc(doi="10.1/nv"))
        sin_doi = await library.add_document(s, world["p1"], **_doc(doi=None, title="Interno"))
        for d in (ok, sin_verificar, sin_doi):
            await library.set_curation(s, world["p1"], d.id, "accepted")
        await library.mark_verified(s, world["p1"], ok.id, "doi_resolved")
        citables = await library.citable_documents(s, world["p1"])
    assert [d.id for d in citables] == [ok.id]
    assert citables[0].verified_at is not None and citables[0].verification_method == "doi_resolved"


@pytest.mark.asyncio
async def test_cannot_verify_a_document_without_doi(world):
    async with AsyncSessionLocal() as s:
        doc = await library.add_document(s, world["p1"], **_doc(doi=None))
        with pytest.raises(ValueError):
            await library.mark_verified(s, world["p1"], doc.id, "doi_resolved")


@pytest.mark.asyncio
async def test_author_supplied_doi_records_who_and_when(world):
    async with AsyncSessionLocal() as s:
        doc = await library.add_document(s, world["p1"], **_doc(doi=None))
        with pytest.raises(ValueError):
            await library.mark_verified(s, world["p1"], doc.id, "author_supplied", doi="10.9/Z")
        d = await library.mark_verified(
            s, world["p1"], doc.id, "author_supplied", verified_by=world["user"], doi="10.9/Z"
        )
    assert d.doi == "10.9/z" and d.verified is True
    assert d.verified_by == world["user"] and d.verified_at is not None


@pytest.mark.asyncio
async def test_verified_without_evidence_is_rejected_by_the_database(world):
    async with AsyncSessionLocal() as s:
        s.add(LibraryDocumentModel(project_id=world["p1"], verified=True, **_doc(doi=None)))
        with pytest.raises(IntegrityError):
            await s.commit()


@pytest.mark.asyncio
async def test_text_status_goes_from_abstract_only_to_full_text(world):
    async with AsyncSessionLocal() as s:
        doc = await library.add_document(s, world["p1"], **_doc())
        d = await library.set_text_status(s, world["p1"], doc.id, "full_text", doc_id="rag-1")
    assert (d.text_status, d.doc_id) == ("full_text", "rag-1")


# --------------------------------------------------------------------------- #
# search_logs (AC6)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_search_log_persists_everything_needed_to_reproduce_it(world):
    when = datetime(2026, 11, 22, 10, 0, 0)
    async with AsyncSessionLocal() as s:
        await library.record_search(
            s, world["p1"], query="graphene AND batteries", sources=["openalex", "crossref"],
            filters={"year_from": 2018}, result_count=40, verified_count=31,
            per_source={"openalex": {"returned": 25}, "crossref": {"returned": 15}},
            discarded={"unresolved": 6, "duplicate": 3}, user_id=world["user"], searched_at=when,
        )
    async with AsyncSessionLocal() as s:
        (log,) = await library.list_searches(s, world["p1"])
    assert log.query == "graphene AND batteries"
    assert log.sources == ["openalex", "crossref"] and log.filters == {"year_from": 2018}
    assert (log.result_count, log.verified_count, log.status) == (40, 31, "completed")
    assert log.searched_at == when and log.user_id == world["user"]
    assert log.discarded == {"unresolved": 6, "duplicate": 3}


@pytest.mark.asyncio
async def test_search_log_defaults_searched_at_to_now_and_validates_status(world):
    async with AsyncSessionLocal() as s:
        log = await library.record_search(s, world["p1"], query="q", sources=[])
        assert abs(datetime.utcnow() - log.searched_at) < timedelta(minutes=1)
        with pytest.raises(ValueError):
            await library.record_search(s, world["p1"], query="q", sources=[], status="weird")
        s.add(SearchLogModel(project_id=world["p1"], query="q", result_count=-1))
        with pytest.raises(IntegrityError):
            await s.commit()


# --------------------------------------------------------------------------- #
# Retención
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_old_search_logs_expire_but_those_of_published_articles_do_not(world):
    viejo = datetime.utcnow() - timedelta(days=settings.RETENTION_SEARCH_LOGS_DAYS + 30)
    async with AsyncSessionLocal() as s:
        pub = ArticleModel(title="Pub", body="b", status=ArticleStatus.PUBLISHED, author_id=world["user"])
        draft = ArticleModel(title="Draft", body="b", status=ArticleStatus.DRAFT, author_id=world["user"])
        s.add_all([pub, draft])
        await s.commit()
        await s.refresh(pub)
        await s.refresh(draft)
        await library.record_search(s, world["p1"], query="publicado", sources=[], article_id=pub.id, searched_at=viejo)
        await library.record_search(s, world["p1"], query="borrador", sources=[], article_id=draft.id, searched_at=viejo)
        await library.record_search(s, world["p1"], query="suelta", sources=[], searched_at=viejo)
        await library.record_search(s, world["p1"], query="reciente", sources=[])
    async with AsyncSessionLocal() as s:
        result = await retention.purge(s, apply=True)
        assert result.counts["search_logs"] == 2
        left = {log.query for log in await library.list_searches(s, world["p1"])}
    assert left == {"publicado", "reciente"}


# --------------------------------------------------------------------------- #
# Migración arriba y abajo
# --------------------------------------------------------------------------- #

def _config(url: str) -> Config:
    config = Config(str(ROOT_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_migration_0008_upgrades_and_downgrades_cleanly(tmp_path):
    path = tmp_path / "m.db"
    cfg = _config(f"sqlite+aiosqlite:///{path.as_posix()}")
    sync = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        command.upgrade(cfg, "head")
        tables = set(inspect(sync).get_table_names())
        assert {"library_documents", "search_logs"} <= tables
        uniques = inspect(sync).get_unique_constraints("library_documents")
        assert any(u["column_names"] == ["project_id", "doi"] for u in uniques)

        command.downgrade(cfg, "0007_integrity_chain")
        tables = set(inspect(sync).get_table_names())
        assert not {"library_documents", "search_logs"} & tables
        assert "agent_run_steps" in tables  # lo anterior sigue intacto

        command.upgrade(cfg, "head")  # y vuelve a subir
        assert "library_documents" in set(inspect(sync).get_table_names())
    finally:
        sync.dispose()
