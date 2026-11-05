"""Consultas de agregación para la portada del proyecto (SPEC-028 / T16.1 / T16.2).

Todas las funciones reciben un ``project_id`` resuelto por ``get_project_context``
y leen únicamente de ``agent_run_steps`` y ``agent_runs`` de ese proyecto.

Las magnitudes definidas (AC2):
- tokens_in / tokens_out: suma de columnas homónimas en agent_run_steps
- latency_ms: **mediana** de los pasos del proyecto (latencia de paso de agente,
  no de petición HTTP); reportado como p50 en la respuesta para ser explícitos.
- articles_analyzed: artículos distintos con al menos un paso terminado en 7 días
- agent_runs_total: filas de agent_runs para el proyecto en 7 días
- failed_steps: pasos con status = 'error' o 'failed'
- Ventana temporal por defecto: últimos 7 días (anclada en el servidor, no en el cliente).

Anomalías definidas (AC3) — cada condición tiene su propio contador:
  1. failed_step: paso con status ∉ {'completed', 'running'}
  2. loop_exhausted: paso con iteration == MAX_REVIEW_LOOPS (3)
  3. latency_exceeded: paso con latency_ms > LATENCY_BUDGET_MS (60 000 ms = 1 min)
  4. rag_empty: paso con len(rag_sources) == 0 y agente != 'publicador' (no recuperó nada)
Cuando el contador es 0 significa «se verificó esta condición y no se encontró ningún caso».
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRunModel
from app.models.agent_run_step import AgentRunStepModel

# Presupuestos declarados (AC3 — no incrustados en la consulta).
MAX_REVIEW_LOOPS: int = 3
LATENCY_BUDGET_MS: float = 60_000.0
WINDOW_DAYS: int = 7

# Agentes que no hacen RAG y deben excluirse del conteo rag_empty.
_NO_RAG_AGENTS = frozenset({"publicador", "formateador"})


async def project_summary(session: AsyncSession, project_id: UUID) -> dict:
    """Agrega las métricas del proyecto en un solo dict.

    Lanza solo consultas sobre filas del ``project_id`` recibido;
    ninguna magnitud puede incluir datos de otro proyecto.
    """
    since = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)

    # -- pasos del proyecto en la ventana temporal --------------------------------
    steps_q = await session.execute(
        select(
            AgentRunStepModel.tokens_in,
            AgentRunStepModel.tokens_out,
            AgentRunStepModel.latency_ms,
            AgentRunStepModel.status,
            AgentRunStepModel.iteration,
            AgentRunStepModel.rag_sources,
            AgentRunStepModel.agent_name,
            AgentRunStepModel.article_id,
        ).where(
            and_(
                AgentRunStepModel.project_id == project_id,
                AgentRunStepModel.created_at >= since,
            )
        )
    )
    steps = steps_q.all()

    tokens_in = sum(r.tokens_in or 0 for r in steps)
    tokens_out = sum(r.tokens_out or 0 for r in steps)
    latencies = [r.latency_ms for r in steps if r.latency_ms]
    latency_p50 = statistics.median(latencies) if latencies else 0.0
    articles_analyzed = len({r.article_id for r in steps if r.article_id})

    # -- agent_runs del proyecto en la ventana -----------------------------------
    runs_q = await session.execute(
        select(func.count(AgentRunModel.run_id)).where(
            and_(
                AgentRunModel.article_id.in_(
                    select(AgentRunStepModel.article_id).where(
                        AgentRunStepModel.project_id == project_id
                    ).distinct()
                ),
                AgentRunModel.started_at >= since,
            )
        )
    )
    agent_runs_total = runs_q.scalar() or 0

    # -- anomalías (AC3) — cuatro condiciones enumeradas -------------------------
    _completed = {"completed"}
    anom_failed = sum(
        1 for r in steps if r.status not in _completed and r.status != "running"
    )
    anom_loop_exhausted = sum(1 for r in steps if (r.iteration or 0) >= MAX_REVIEW_LOOPS)
    anom_latency = sum(1 for r in steps if (r.latency_ms or 0.0) > LATENCY_BUDGET_MS)
    anom_rag_empty = sum(
        1 for r in steps
        if r.agent_name not in _NO_RAG_AGENTS and not (r.rag_sources or [])
    )

    return {
        "window_days": WINDOW_DAYS,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens_total": tokens_in + tokens_out,
        "latency_p50_ms": round(latency_p50, 1),
        "articles_analyzed": articles_analyzed,
        "agent_runs_total": agent_runs_total,
        "steps_total": len(steps),
        # Anomalías — cuatro condiciones verificadas; 0 significa «comprobado, ningún caso».
        "anomalies": {
            "failed_step": anom_failed,
            "loop_exhausted": anom_loop_exhausted,
            "latency_exceeded": anom_latency,
            "rag_empty": anom_rag_empty,
            "total": anom_failed + anom_loop_exhausted + anom_latency + anom_rag_empty,
            # Semántica explícita: qué se comprobó (AC3 — el cero significa algo).
            "checks_applied": ["failed_step", "loop_exhausted", "latency_exceeded", "rag_empty"],
        },
        # Parámetros de los umbrales para que la UI pueda decir cuál es el presupuesto.
        "budgets": {
            "latency_budget_ms": LATENCY_BUDGET_MS,
            "max_review_loops": MAX_REVIEW_LOOPS,
        },
    }


async def project_articles_summary(session: AsyncSession, project_id: UUID) -> list[dict]:
    """Estado real del pipeline y coste en tokens por artículo del proyecto (AC5).

    Lee de agent_run_steps, no del campo status de ArticleModel, que puede haber
    quedado desfasado respecto a la última ejecución.
    """
    since = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)

    steps_q = await session.execute(
        select(
            AgentRunStepModel.article_id,
            AgentRunStepModel.agent_name,
            AgentRunStepModel.tokens_in,
            AgentRunStepModel.tokens_out,
            AgentRunStepModel.latency_ms,
            AgentRunStepModel.status,
            AgentRunStepModel.created_at,
        ).where(
            and_(
                AgentRunStepModel.project_id == project_id,
                AgentRunStepModel.created_at >= since,
            )
        ).order_by(AgentRunStepModel.created_at)
    )
    rows = steps_q.all()

    by_article: dict[UUID, dict] = {}
    for r in rows:
        aid = r.article_id
        if aid not in by_article:
            by_article[aid] = {
                "article_id": str(aid),
                "tokens_in": 0,
                "tokens_out": 0,
                "agents_run": set(),
                "failed": False,
                "last_run": None,
            }
        by_article[aid]["tokens_in"] += r.tokens_in or 0
        by_article[aid]["tokens_out"] += r.tokens_out or 0
        by_article[aid]["agents_run"].add(r.agent_name)
        if r.status not in {"completed", "running"}:
            by_article[aid]["failed"] = True
        by_article[aid]["last_run"] = r.created_at

    result = []
    for item in by_article.values():
        item["agents_run"] = sorted(item["agents_run"])
        item["tokens_total"] = item["tokens_in"] + item["tokens_out"]
        result.append(item)
    return result
