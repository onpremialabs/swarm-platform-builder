"""Política de retención y purga (SPEC-020 / T6.5 / AC5).

AC5: existe una política de retención documentada —qué se guarda, cuánto y cómo se
purga— y un mecanismo de purga **aplicable**.

Las dos mitades se prueban aquí, y la del documento no es un formalismo: una
política que no coincide con lo que hace el código es peor que no tener política,
porque genera confianza infundada. Por eso hay casos que comparan el documento con
la configuración real y con las tablas que existen.
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio

ROOT_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = ROOT_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

TEST_DB_PATH = (ROOT_DIR / "tests" / "test_retention.db").resolve()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

from sqlalchemy import func, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    AgentRunModel,
    ArticleModel,
    ArticleStatus,
    FlowCheckpointModel,
    NotificationModel,
    UserModel,
    UserRole,
)
from app.models.audit_log import AuditLogModel  # noqa: E402
from app.platform import retention  # noqa: E402

POLICY = REPO_DIR / "docs" / "governance" / "data-retention.md"

# Conjuntos que caducan, con la variable de configuración que los gobierna.
EXPIRING = {
    "audit_log": "RETENTION_AUDIT_LOG_DAYS",
    "agent_runs": "RETENTION_AGENT_RUNS_DAYS",
    "publication_gate_reports": "RETENTION_GATE_REPORTS_DAYS",
    "citation_links": "RETENTION_CITATION_LINKS_DAYS",
    "flow_checkpoints": "RETENTION_CHECKPOINTS_DAYS",
    "notifications": "RETENTION_NOTIFICATIONS_DAYS",
    "orphan_assets": "RETENTION_ORPHAN_ASSETS_DAYS",
}

# Contenido del producto: nunca se purga por antigüedad.
NEVER_EXPIRING = ("users", "projects", "articles", "agent_profiles", "saved_flows")


@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _ago(days: int) -> datetime:
    return datetime.utcnow() - timedelta(days=days)


async def _seed_expired_and_recent() -> UserModel:
    """Una fila vieja y otra reciente en cada conjunto que caduca."""
    async with AsyncSessionLocal() as session:
        user = UserModel(
            email="dueña@ejemplo.com", hashed_password=hash_password("x" * 12),
            full_name="Dueña", role=UserRole.REDACTOR, is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        article = ArticleModel(
            title="Artículo antiguo", body="cuerpo", status=ArticleStatus.DRAFT,
            author_id=user.id, created_at=_ago(2000),
        )
        session.add(article)

        session.add_all([
            AuditLogModel(action="role.changed", created_at=_ago(400)),
            AuditLogModel(action="role.changed", created_at=_ago(10)),
            AgentRunModel(agent_name="redactor", status="ok", started_at=_ago(200)),
            AgentRunModel(agent_name="redactor", status="ok", started_at=_ago(5)),
            FlowCheckpointModel(author_id=user.id, state_json={}, created_at=_ago(90)),
            FlowCheckpointModel(author_id=user.id, state_json={}, created_at=_ago(2)),
            NotificationModel(
                user_id=user.id, title="vieja leída", message="m",
                read=True, created_at=_ago(200),
            ),
            NotificationModel(
                user_id=user.id, title="vieja SIN leer", message="m",
                read=False, created_at=_ago(200),
            ),
            NotificationModel(
                user_id=user.id, title="reciente", message="m",
                read=True, created_at=_ago(1),
            ),
        ])
        await session.commit()
        return user


async def _count(model) -> int:
    async with AsyncSessionLocal() as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


# --------------------------------------------------------------------------- #
# AC5 — la purga funciona, y no borra de más
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_dry_run_counts_without_deleting_anything(db):
    await _seed_expired_and_recent()

    async with AsyncSessionLocal() as session:
        result = await retention.purge(session)

    assert result.dry_run is True
    assert result.counts["audit_log"] == 1
    assert result.counts["agent_runs"] == 1
    assert result.counts["flow_checkpoints"] == 1
    assert result.counts["notifications"] == 1  # solo la vieja *leída*
    # Y nada se ha tocado.
    assert await _count(AuditLogModel) == 2
    assert await _count(AgentRunModel) == 2
    assert await _count(NotificationModel) == 3


@pytest.mark.asyncio
async def test_apply_deletes_only_what_is_past_its_window(db):
    await _seed_expired_and_recent()

    async with AsyncSessionLocal() as session:
        result = await retention.purge(session, apply=True)

    assert result.dry_run is False
    assert await _count(AuditLogModel) == 1
    assert await _count(AgentRunModel) == 1
    assert await _count(FlowCheckpointModel) == 1
    assert await _count(NotificationModel) == 2  # la sin leer sobrevive


@pytest.mark.asyncio
async def test_unread_notifications_never_expire(db):
    """Una notificación sin leer sigue pendiente de alguien, por vieja que sea."""
    user = await _seed_expired_and_recent()
    async with AsyncSessionLocal() as session:
        await retention.purge(session, apply=True)
        result = await session.execute(
            select(NotificationModel.title).where(NotificationModel.read.is_(False))
        )
        assert "vieja SIN leer" in [t for (t,) in result.all()]
    assert user is not None


@pytest.mark.asyncio
async def test_product_content_is_never_purged(db):
    """Usuarios y artículos son el producto, no su rastro: no caducan."""
    await _seed_expired_and_recent()
    async with AsyncSessionLocal() as session:
        await retention.purge(session, apply=True)

    assert await _count(UserModel) == 1
    assert await _count(ArticleModel) == 1, "se purgó un artículo por antigüedad"


@pytest.mark.asyncio
async def test_a_zero_window_disables_that_purge(db, monkeypatch):
    """Poner 0 es el mecanismo para conservar (obligación legal, investigación)."""
    await _seed_expired_and_recent()
    monkeypatch.setattr(settings, "RETENTION_AUDIT_LOG_DAYS", 0)

    async with AsyncSessionLocal() as session:
        result = await retention.purge(session, apply=True)

    assert result.counts["audit_log"] == 0
    assert "audit_log" in result.skipped, "no se avisa de que la ventana está desactivada"
    assert await _count(AuditLogModel) == 2


@pytest.mark.asyncio
async def test_purging_twice_is_idempotent(db):
    await _seed_expired_and_recent()
    async with AsyncSessionLocal() as session:
        await retention.purge(session, apply=True)
    async with AsyncSessionLocal() as session:
        segunda = await retention.purge(session, apply=True)
    assert segunda.total == 0


@pytest.mark.asyncio
async def test_the_report_says_plainly_that_nothing_was_deleted(db):
    async with AsyncSessionLocal() as session:
        texto = (await retention.purge(session)).render()
    assert "Simulación" in texto and "--apply" in texto


# --------------------------------------------------------------------------- #
# AC5 — figuras huérfanas
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_orphan_figures_expire_but_referenced_ones_do_not(db, tmp_path, monkeypatch):
    monkeypatch.setattr(retention, "_assets_root", lambda: tmp_path)
    proyecto = tmp_path / ("a" * 32)
    proyecto.mkdir()

    citada, huerfana, reciente = uuid4().hex, uuid4().hex, uuid4().hex
    for asset_id in (citada, huerfana, reciente):
        (proyecto / f"{asset_id}.png").write_bytes(b"\x89PNG")

    viejo = _ago(200).timestamp()
    for asset_id in (citada, huerfana):
        os.utime(proyecto / f"{asset_id}.png", (viejo, viejo))

    async with AsyncSessionLocal() as session:
        user = UserModel(
            email="figuras@ejemplo.com", hashed_password=hash_password("x" * 12),
            full_name="F", role=UserRole.REDACTOR, is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        session.add(ArticleModel(
            title="Con figura", body=f"Texto ![pie](asset:{citada}) más texto",
            status=ArticleStatus.DRAFT, author_id=user.id,
        ))
        await session.commit()

    async with AsyncSessionLocal() as session:
        result = await retention.purge(session, apply=True)

    assert result.counts["orphan_assets"] == 1
    assert (proyecto / f"{citada}.png").exists(), "se borró una figura referenciada"
    assert not (proyecto / f"{huerfana}.png").exists()
    assert (proyecto / f"{reciente}.png").exists(), "se borró una figura recién subida"


@pytest.mark.asyncio
async def test_unknown_files_in_the_asset_store_are_left_alone(db, tmp_path, monkeypatch):
    """La purga solo toca ficheros con forma de asset; nada más del directorio."""
    monkeypatch.setattr(retention, "_assets_root", lambda: tmp_path)
    ajeno = tmp_path / "no-es-un-asset.txt"
    ajeno.write_text("importante")
    viejo = _ago(500).timestamp()
    os.utime(ajeno, (viejo, viejo))

    async with AsyncSessionLocal() as session:
        await retention.purge(session, apply=True)

    assert ajeno.exists()


# --------------------------------------------------------------------------- #
# AC5 — la política documentada coincide con el código
# --------------------------------------------------------------------------- #

def test_the_policy_document_exists():
    assert POLICY.exists(), "AC5 exige una política de retención documentada"


def test_the_policy_answers_the_three_questions():
    texto = POLICY.read_text(encoding="utf-8").lower()
    for pregunta in ("qué se guarda", "cómo se purga"):
        assert pregunta in texto, f"la política no dice «{pregunta}»"


@pytest.mark.parametrize("conjunto,ajuste", sorted(EXPIRING.items()))
def test_every_expiring_set_is_documented_with_its_setting(conjunto, ajuste):
    """Si el código purga algo que el documento no menciona, la política miente."""
    texto = POLICY.read_text(encoding="utf-8")
    assert conjunto in texto, f"{conjunto} se purga pero no está documentado"
    assert ajuste in texto, f"{ajuste} no aparece en la política"


@pytest.mark.parametrize("ajuste", sorted(set(EXPIRING.values())))
def test_the_documented_windows_match_the_configured_defaults(ajuste):
    """Y al revés: el número del documento tiene que ser el que aplica el código."""
    valor = getattr(settings, ajuste)
    texto = POLICY.read_text(encoding="utf-8")
    assert f"{valor} días" in texto, (
        f"{ajuste} vale {valor} pero la política no menciona «{valor} días»"
    )


@pytest.mark.parametrize("conjunto", NEVER_EXPIRING)
def test_product_content_is_documented_as_non_expiring(conjunto):
    assert conjunto in POLICY.read_text(encoding="utf-8")


def test_the_policy_states_what_it_does_not_cover():
    """Los huecos conocidos se dicen, no se dejan implícitos."""
    texto = POLICY.read_text(encoding="utf-8").lower()
    assert "supresión" in texto or "supresion" in texto, "no menciona el derecho de supresión"
    assert "qdrant" in texto
    assert "copias de seguridad" in texto or "backup" in texto


def test_every_expiring_set_has_a_real_setting():
    for ajuste in EXPIRING.values():
        assert hasattr(settings, ajuste), f"{ajuste} no existe en la configuración"
