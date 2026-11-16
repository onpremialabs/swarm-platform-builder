"""Portada de proyecto — métricas del enjambre (SPEC-028 / T16.2, T16.4, T16.6).

``GET /api/v1/dashboard/summary`` devuelve en una sola petición las magnitudes de la
portada para el proyecto activo.  El aislamiento es obligatorio: la dependencia
``get_project_context`` resuelve y autoriza el proyecto desde la cabecera
``X-Project-Id``, igual que el resto de rutas que leen datos del proyecto.
No reutiliza ``GET /metrics``, que es anónima y sin proyecto.

**Cada sección responde por sí sola (AC7).** Antes la respuesta se componía con
tres ``await`` seguidos: si uno fallaba, la petición entera devolvía 500 y la
portada se quedaba a cero —indistinguible de «no hay datos», que es el error que
esta misma spec persigue en el AC3—. Ahora cada agregación va en su propio intento
y la respuesta declara en ``sections`` cuáles pudieron calcularse. Lo que no se
pudo preguntar se dice; no se rellena con ceros.
"""
import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.stream_auth import consume_project_ticket, issue_project_ticket
from app.platform.bus import get_bus
from app.platform.project_access import get_project_context
from app.platform.project_context import ProjectContext
from app.platform.summary import (
    project_articles_summary, project_executions, project_summary,
    project_swarm_state,
)
from app.routers.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

#: Valor con el que se responde una sección que no se pudo calcular. No es «el
#: dato en cero»: la UI lo distingue mirando `sections[...]["available"]`.
_VACIO = {
    "metrics": {},
    "swarm": {"stale_after_s": 0, "criteria": {}, "agents": []},
    "articles": [],
    "executions": [],
}


async def _seccion(session: AsyncSession, nombre: str, fuente: str, calcular, estado: dict):
    """Calcula una sección y anota si se pudo; nunca propaga el fallo.

    El ``rollback`` no es decorativo: tras un error la sesión de SQLAlchemy queda
    inutilizable, y sin él la primera sección rota tumbaría también las
    siguientes, que es exactamente la degradación en cascada que AC7 prohíbe.
    """
    try:
        valor = await calcular()
        estado[nombre] = {"available": True, "source": fuente}
        return valor
    except Exception as exc:
        await session.rollback()
        logger.warning(
            "La portada no pudo calcular la sección %s", nombre,
            extra={"event": "dashboard_section_unavailable", "seccion": nombre,
                   "fuente": fuente, "error": type(exc).__name__},
            exc_info=True,
        )
        estado[nombre] = {
            "available": False, "source": fuente, "reason": type(exc).__name__,
        }
        return _VACIO[nombre]


@router.get("/summary")
async def get_dashboard_summary(
    project: ProjectContext = Depends(get_project_context),
    session: AsyncSession = Depends(get_session),
):
    """Métricas de la portada para el proyecto activo (AC1–AC7).

    Todas las magnitudes se leen únicamente de las filas del proyecto resuelto
    por ``get_project_context``; ningún dato de otro proyecto puede aparecer aquí.

    Magnitudes devueltas (AC2 — qué cuenta cada campo):
    - ``tokens_in`` / ``tokens_out``: suma de tokens de entrada/salida de todos
      los pasos del proyecto en los últimos 7 días (de ``agent_run_steps``).
    - ``latency_p50_ms``: mediana de ``latency_ms`` por paso de agente —no de
      petición HTTP— en los últimos 7 días.
    - ``articles_analyzed``: artículos distintos con al menos un paso en 7 días.
    - ``executions_total``: pasadas del pipeline, separadas por ``step_index``
      volviendo a 0. No son filas de ``agent_runs``, que se minan por paso.
    - ``anomalies``: cuatro condiciones enumeradas sobre la traza (AC3); el cero
      significa «se comprobó esta condición y no se encontró ningún caso».
    - ``swarm``: estado de cada agente derivado de los pasos abiertos (AC4), con
      el criterio de cada estado escrito en la propia respuesta.
    - ``executions``: una fila por pasada del pipeline (SPEC-029 / AC1).
    - ``sections``: qué se pudo calcular y qué no (AC7). Una sección con
      ``available: false`` **no** trae datos en cero: no se pudo preguntar.
    """
    pid = project.project_id
    sections: dict[str, dict] = {}

    metrics = await _seccion(
        session, "metrics", "database", lambda: project_summary(session, pid), sections)
    swarm = await _seccion(
        session, "swarm", "database", lambda: project_swarm_state(session, pid), sections)
    articles = await _seccion(
        session, "articles", "database", lambda: project_articles_summary(session, pid), sections)
    executions = await _seccion(
        session, "executions", "database", lambda: project_executions(session, pid), sections)

    return {
        **metrics,
        "swarm": swarm,
        "articles": articles,
        "executions": executions,
        "sections": sections,
    }


@router.post("/log-ticket")
async def create_project_log_ticket(
    project: ProjectContext = Depends(get_project_context),
    token_data=Depends(get_current_user),
):
    """Ticket de un solo uso para el log en vivo del proyecto (T17.5).

    Mismo motivo que el de artículo: `EventSource` no manda cabecera
    `Authorization`, y poner el JWT en el query string lo filtra a logs, historial
    y proxies. El ticket queda atado a **este** proyecto, ya autorizado por
    `get_project_context`.
    """
    ticket = await issue_project_ticket(token_data["user_id"], str(project.project_id))
    return {"ticket": ticket}


@router.get("/log-stream")
async def stream_project_log(
    ticket: str | None = None,
    project: ProjectContext = Depends(get_project_context),
):
    """Log en vivo del proyecto activo (SPEC-029 / T17.5 / AC2).

    **El filtro es de servidor.** El bus entrega a este flujo solo los eventos de
    artículos vinculados a este proyecto: uno de otro proyecto no llega al
    cliente ni siquiera para descartarse en el navegador. Filtrar en el cliente
    habría significado mandárselo primero, que es exactamente la fuga que AC2
    quiere evitar en la vista pensada para auditar.

    Un artículo sin vincular no emite aquí. Ante la duda no se entrega: perder
    una línea del log molesta; entregarla al proyecto ajeno rompe T8.5.
    """
    user_id = await consume_project_ticket(ticket, str(project.project_id)) if ticket else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Ticket de stream ausente o no válido")

    async def eventos():
        async with get_bus().subscribe_project(project.project_id) as cola:
            try:
                while True:
                    try:
                        evento = await asyncio.wait_for(cola.get(), timeout=20)
                    except asyncio.TimeoutError:
                        # Comentario SSE: mantiene viva la conexión a través de
                        # proxies que cortan por inactividad, sin inventarse un
                        # evento que el cliente tendría que aprender a ignorar.
                        yield ": keep-alive\n\n"
                        continue
                    yield f"data: {json.dumps(evento, default=str)}\n\n"
            except asyncio.CancelledError:
                raise

    return StreamingResponse(eventos(), media_type="text/event-stream")
