"""Portada de proyecto — métricas del enjambre (SPEC-028 / T16.2).

``GET /dashboard/summary`` devuelve en una sola petición las magnitudes de la
portada para el proyecto activo.  El aislamiento es obligatorio: la dependencia
``get_project_context`` resuelve y autoriza el proyecto desde la cabecera
``X-Project-Id``, igual que el resto de rutas que leen datos del proyecto.
No reutiliza ``GET /metrics``, que es anónima y sin proyecto.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.platform.project_access import get_project_context
from app.platform.project_context import ProjectContext
from app.platform.summary import project_articles_summary, project_summary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
async def get_dashboard_summary(
    project: ProjectContext = Depends(get_project_context),
    session: AsyncSession = Depends(get_session),
):
    """Métricas de la portada para el proyecto activo (AC1, AC2, AC3, AC5).

    Todas las magnitudes se leen únicamente de las filas del proyecto resuelto
    por ``get_project_context``; ningún dato de otro proyecto puede aparecer aquí.

    Magnitudes devueltas (AC2 — qué cuenta cada campo):
    - ``tokens_in`` / ``tokens_out``: suma de tokens de entrada/salida de todos
      los pasos del proyecto en los últimos 7 días (de ``agent_run_steps``).
    - ``latency_p50_ms``: mediana de ``latency_ms`` por paso de agente —no de
      petición HTTP— en los últimos 7 días.
    - ``articles_analyzed``: artículos distintos con al menos un paso en 7 días.
    - ``agent_runs_total``: filas en ``agent_runs`` ligadas al proyecto en 7 días.
    - ``anomalies``: cuatro condiciones enumeradas sobre la traza (AC3); el cero
      significa «se comprobó esta condición y no se encontró ningún caso».
    """
    summary = await project_summary(session, project.project_id)
    articles = await project_articles_summary(session, project.project_id)
    return {
        **summary,
        "articles": articles,
    }
