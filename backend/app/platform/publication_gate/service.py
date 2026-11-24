"""Persistencia y lectura del informe de la compuerta (SPEC-032 AC6).

El informe vigente de un artículo es el **último cuya huella coincide con su
cuerpo**: si el texto cambió desde la evaluación, ese informe ya no describe lo
que se publicaría y hay que reevaluar. Cada evaluación inserta una fila nueva; no
se sobrescribe.
"""
import hashlib
import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import ArticleModel
from app.models.publication_gate_report import PublicationGateReportModel
from app.platform.publication_gate.config import GateConfig
from app.platform.publication_gate.gate import GateReport, evaluate_gate
from app.platform.publication_gate.reference_resolver import CRITERION as EXISTENCE
from app.platform.publication_gate.types import CriterionResult, CriterionStatus


logger = logging.getLogger(__name__)


def text_sha256(text: Optional[str]) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


async def latest_report(session: AsyncSession, article_id: UUID) -> Optional[PublicationGateReportModel]:
    result = await session.execute(
        select(PublicationGateReportModel)
        .where(PublicationGateReportModel.article_id == article_id)
        .order_by(PublicationGateReportModel.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


def is_current(report: Optional[PublicationGateReportModel], article: ArticleModel) -> bool:
    """¿El informe describe el texto actual del artículo?"""
    return report is not None and report.text_sha256 == text_sha256(article.body)


async def _run_judge(citations, config: GateConfig, agent_settings, judge_call) -> None:
    """Juzga las citas pendientes (T23.4). Un juez no independiente o caído no aborta la
    evaluación: las citas quedan `not_verified` (`judge_unavailable`) y el informe lo dice."""
    from app.platform.publication_gate.citation_judge import JudgeConfigError, judge_links

    try:
        await judge_links(
            citations, config.citation_support_min_overlap,
            agent_settings=agent_settings, call=judge_call,
        )
    except JudgeConfigError as exc:
        logger.error("Juez de citas no disponible: %s", exc)
    except Exception as exc:  # falla cerrada, sin tumbar la compuerta
        logger.error("El juez de citas abortó (%s): %s", type(exc).__name__, exc)


async def evaluate_and_store(
    session: AsyncSession,
    article: ArticleModel,
    config: GateConfig,
    sources: Optional[list] = None,
    *,
    run_id: Optional[UUID] = None,
    created_by: Optional[UUID] = None,
    review: Optional[dict] = None,
    citation_map_unavailable: bool = False,
    agent_settings: Optional[dict] = None,
    judge_call: Any = None,
    **resolver_kwargs: Any,
) -> tuple[PublicationGateReportModel, GateReport]:
    """Evalúa el texto actual del artículo y guarda el informe (sin hacer commit)."""
    citations = None
    if config.citation_support_min_overlap is not None:
        from app.platform.citations import current_citation_map
        # Si el guardado del mapa falló, `None` -> `map_unavailable` (not_verified), no se omite.
        citations = None if citation_map_unavailable else await current_citation_map(session, article)
        if config.citation_judge and citations:
            await _run_judge(citations, config, agent_settings, judge_call)
    report = await evaluate_gate(
        article.body or "", sources or [], config,
        created_at=getattr(article, "created_at", None), citations=citations,
        **resolver_kwargs,
    )
    if not sources:
        # Sin fuentes estructuradas no hay nada que resolver, y un manuscrito sin
        # referencias comprobables no se aprueba por ausencia (ADR-0011).
        report.criteria[0] = CriterionResult(
            EXISTENCE, CriterionStatus.NOT_VERIFIED,
            [{"index": 0, "title": "", "status": "not_verified",
              "reason": "no hay referencias estructuradas que comprobar"}],
        )
    criteria = report.as_dict()
    if review is not None:
        # La revisión que acompañó a este texto: `can_publish` la lee de aquí, porque
        # fuera del pipeline ya no queda rastro de ella (SPEC-032/AC10).
        criteria["review"] = review
    row = PublicationGateReportModel(
        article_id=article.id,
        run_id=run_id,
        text_sha256=text_sha256(article.body),
        criteria=criteria,
        sources=report.sources,
        created_by=created_by,
    )
    session.add(row)
    await session.flush()
    return row, report
