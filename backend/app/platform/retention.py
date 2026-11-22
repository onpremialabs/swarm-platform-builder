"""Purga por política de retención (SPEC-020 / T6.5 / AC5).

Aplica las ventanas de `docs/governance/data-retention.md`. Cada conjunto se trata
por separado porque cada uno tiene un motivo distinto para caducar: el audit log es
evidencia de seguridad, las ejecuciones de agentes guardan lo que el usuario
escribió, los checkpoints son puntos de reanudación que dejan de servir enseguida,
y las figuras huérfanas son binarios que ya nadie referencia.

**Simulación por defecto.** `purge()` cuenta y no borra salvo que se le pase
`apply=True`, igual que `/sdd-sync`. Una purga es irreversible y se ejecuta sobre
producción: el modo por defecto tiene que ser el que no destruye nada.

**Solo caduca lo que es registro, nunca el contenido.** Usuarios, proyectos,
artículos, perfiles de agente y flujos guardados **no** se purgan por antigüedad:
son el producto, no su rastro. Borrarlos por edad destruiría el trabajo de alguien,
y su eliminación es una decisión explícita del propietario, no de un cron.

Uso:

    python -m app.platform.retention              # simula y muestra qué caducaría
    python -m app.platform.retention --apply      # ejecuta la purga
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.agent_run import AgentRunModel
from app.models.agent_run_step import AgentRunStepModel
from app.models.article import ArticleModel
from app.models.audit_log import AuditLogModel
from app.models.checkpoint import FlowCheckpointModel
from app.models.notification import NotificationModel
from app.models.enums import ArticleStatus
from app.models.publication_gate_report import PublicationGateReportModel
from app.models.search_log import SearchLogModel

logger = logging.getLogger(__name__)

_ASSET_FILENAME_RE = re.compile(r"^([0-9a-f]{32})\.[a-z0-9]+$", re.IGNORECASE)
_ASSET_REF_IN_BODY_RE = re.compile(r"asset:([0-9a-f]{32})", re.IGNORECASE)


@dataclass
class PurgeResult:
    """Qué caducó (o caducaría) en cada conjunto."""

    dry_run: bool
    counts: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def render(self) -> str:
        verbo = "caducarían" if self.dry_run else "purgados"
        lineas = [f"Retención — {verbo}:"]
        for nombre, cantidad in sorted(self.counts.items()):
            lineas.append(f"  {nombre:22} {cantidad}")
        for nombre, motivo in sorted(self.skipped.items()):
            lineas.append(f"  {nombre:22} — sin purgar ({motivo})")
        lineas.append(f"  {'TOTAL':22} {self.total}")
        if self.dry_run:
            lineas.append("\nSimulación: no se ha borrado nada. Ejecuta con --apply.")
        return "\n".join(lineas)


def _cutoff(days: int) -> datetime | None:
    """Fecha límite, o ``None`` si la ventana está desactivada (0 o negativa)."""
    if days is None or days <= 0:
        return None
    return datetime.utcnow() - timedelta(days=days)


async def _purge_table(
    session: AsyncSession, model, column, days: int, *, apply: bool, extra=None
) -> tuple[int, str | None]:
    cutoff = _cutoff(days)
    if cutoff is None:
        return 0, "ventana desactivada (0 días)"

    filtros = [column < cutoff]
    if extra is not None:
        filtros.append(extra)

    total = await session.scalar(select(func.count()).select_from(model).where(*filtros))
    total = int(total or 0)
    if apply and total:
        await session.execute(delete(model).where(*filtros))
    return total, None


def _assets_root() -> Path:
    """Raíz del almacén de figuras, resuelta como en `app.platform.assets`."""
    for candidate in (Path("app/.assets"), Path("../app/.assets")):
        if candidate.exists():
            return candidate
    return Path("app/.assets")


async def _referenced_asset_ids(session: AsyncSession) -> set[str]:
    """Ids de figura citados por el cuerpo de algún artículo."""
    referenced: set[str] = set()
    result = await session.execute(select(ArticleModel.body))
    for (body,) in result.all():
        if body:
            referenced.update(m.lower() for m in _ASSET_REF_IN_BODY_RE.findall(body))
    return referenced


async def _purge_orphan_assets(
    session: AsyncSession, days: int, *, apply: bool
) -> tuple[int, str | None]:
    """Borra figuras que ningún artículo referencia y que ya no son recientes.

    La antigüedad no es un detalle: una figura recién subida todavía no aparece en
    el cuerpo —el usuario aún no ha pegado la referencia—, así que purgar por
    «huérfana» sin margen borraría justo lo que se acaba de subir.
    """
    cutoff = _cutoff(days)
    if cutoff is None:
        return 0, "ventana desactivada (0 días)"

    root = _assets_root()
    if not root.exists():
        return 0, None

    referenced = await _referenced_asset_ids(session)
    limite = cutoff.timestamp()
    borrados = 0

    for archivo in root.rglob("*"):
        if not archivo.is_file():
            continue
        match = _ASSET_FILENAME_RE.match(archivo.name)
        if not match:
            continue
        if match.group(1).lower() in referenced:
            continue
        if archivo.stat().st_mtime >= limite:
            continue
        borrados += 1
        if apply:
            archivo.unlink(missing_ok=True)

    return borrados, None


async def purge(session: AsyncSession, *, apply: bool = False) -> PurgeResult:
    """Aplica todas las ventanas de retención. Sin `apply=True` solo cuenta."""
    result = PurgeResult(dry_run=not apply)

    conjuntos: Iterable[tuple[str, object, object, int, object]] = (
        ("audit_log", AuditLogModel, AuditLogModel.created_at,
         settings.RETENTION_AUDIT_LOG_DAYS, None),
        ("agent_runs", AgentRunModel, AgentRunModel.started_at,
         settings.RETENTION_AGENT_RUNS_DAYS, None),
        ("agent_run_steps", AgentRunStepModel, AgentRunStepModel.created_at,
         settings.RETENTION_AGENT_RUN_STEPS_DAYS, None),
        ("flow_checkpoints", FlowCheckpointModel, FlowCheckpointModel.created_at,
         settings.RETENTION_CHECKPOINTS_DAYS, None),
        # Informes de la compuerta (SPEC-032/AC16): se conservan mientras el artículo
        # esté publicado, porque son la evidencia de por qué se aprobó; los demás
        # caducan a la par que las ejecuciones del pipeline.
        ("gate_reports", PublicationGateReportModel, PublicationGateReportModel.created_at,
         settings.RETENTION_GATE_REPORTS_DAYS,
         PublicationGateReportModel.article_id.notin_(
             select(ArticleModel.id).where(ArticleModel.status == ArticleStatus.PUBLISHED)
         )),
        # Registro de búsqueda bibliográfica (SPEC-034/AC6): es el apartado de métodos
        # del artículo, así que el de un artículo publicado no caduca. Los demás
        # (borradores, búsquedas sin artículo) sí.
        ("search_logs", SearchLogModel, SearchLogModel.searched_at,
         settings.RETENTION_SEARCH_LOGS_DAYS,
         or_(
             SearchLogModel.article_id.is_(None),
             SearchLogModel.article_id.notin_(
                 select(ArticleModel.id).where(ArticleModel.status == ArticleStatus.PUBLISHED)
             ),
         )),
        # Solo las ya leídas: una notificación sin leer sigue siendo pendiente de
        # alguien, por vieja que sea.
        ("notifications", NotificationModel, NotificationModel.created_at,
         settings.RETENTION_NOTIFICATIONS_DAYS, NotificationModel.read.is_(True)),
    )

    for nombre, model, column, days, extra in conjuntos:
        cantidad, motivo = await _purge_table(
            session, model, column, days, apply=apply, extra=extra
        )
        result.counts[nombre] = cantidad
        if motivo:
            result.skipped[nombre] = motivo

    cantidad, motivo = await _purge_orphan_assets(
        session, settings.RETENTION_ORPHAN_ASSETS_DAYS, apply=apply
    )
    result.counts["orphan_assets"] = cantidad
    if motivo:
        result.skipped["orphan_assets"] = motivo

    if apply:
        await session.commit()
        logger.info(
            "Purga de retención aplicada: %s registros", result.total,
            extra={"event": "retention_purge", "counts": result.counts},
        )
    return result


async def _main(apply: bool) -> PurgeResult:
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return await purge(session, apply=apply)


if __name__ == "__main__":  # pragma: no cover - punto de entrada del script
    parser = argparse.ArgumentParser(description="Purga por política de retención")
    parser.add_argument(
        "--apply", action="store_true",
        help="Ejecuta la purga. Sin este flag solo se simula y no se borra nada.",
    )
    args = parser.parse_args()
    print(asyncio.run(_main(args.apply)).render())
