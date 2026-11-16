"""Consultas de agregación para la portada del proyecto (SPEC-028 / T16.1 / T16.2).

Todas las funciones reciben un ``project_id`` resuelto por ``get_project_context``
y leen únicamente de ``agent_run_steps`` y ``agent_runs`` de ese proyecto.

Las magnitudes definidas (AC2):
- tokens_in / tokens_out: suma de columnas homónimas en agent_run_steps
- latency_ms: **mediana** de los pasos del proyecto (latencia de paso de agente,
  no de petición HTTP); reportado como p50 en la respuesta para ser explícitos.
- articles_analyzed: artículos distintos con al menos un paso terminado en 7 días
- executions_total: pasadas del pipeline, separadas por `step_index` volviendo a 0.
  No son filas de `agent_runs`: ahí se mina un run_id **por paso**, así que contar
  esa tabla daba el número de pasos disfrazado de número de ejecuciones.
- failed_steps: pasos con status = 'error' o 'failed'
- by_agent: el mismo consumo (ejecuciones, tokens, latencia, errores) agrupado por
  agente. Se agrega aquí, no en el cliente: la fila ya trae el agente y sus
  tokens, y el cliente solo recibe el resumen, no los pasos.
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

from app.models.agent_profile import AgentProfileModel
from app.models.agent_run import AgentRunModel
from app.models.agent_run_step import AgentRunStepModel
from app.models.article import ArticleModel
from app.platform.explainability import group_executions

# Presupuestos declarados (AC3 — no incrustados en la consulta).
MAX_REVIEW_LOOPS: int = 3
LATENCY_BUDGET_MS: float = 60_000.0
WINDOW_DAYS: int = 7

#: Umbral de incertidumbre del estado del enjambre (AC4). Un proceso que muere
#: deja su fila de `agent_runs` en 'running' para siempre; pasado este tiempo el
#: paso deja de contar como «ejecutando» y pasa a «incierto», que es lo que de
#: verdad se sabe. Holgado respecto a `LATENCY_BUDGET_MS` a propósito: superar el
#: presupuesto de latencia es una anomalía, no una señal de que el proceso murió.
SWARM_STALE_AFTER_S: int = 900

#: Qué significa cada estado, en la respuesta y no solo en el código: AC4 pide que
#: «el criterio de cada uno esté escrito», y un criterio que vive únicamente en el
#: backend se desincroniza del rótulo que lee quien mira la portada.
SWARM_CRITERIA: dict[str, str] = {
    "ejecutando": (
        "Tiene un paso abierto —fila en agent_runs con status 'running' y sin "
        f"finished_at— empezado hace menos de {SWARM_STALE_AFTER_S // 60} min."
    ),
    "incierto": (
        f"Tiene un paso abierto desde hace más de {SWARM_STALE_AFTER_S // 60} min. "
        "No se afirma que esté ejecutando: lo normal a esas alturas es que el "
        "proceso muriera sin cerrar el paso."
    ),
    "disponible": "Tiene perfil en el proyecto y ningún paso abierto.",
    "no_configurado": (
        "Aparece en la traza del proyecto pero ya no tiene perfil: se borró o se "
        "renombró después de ejecutarse."
    ),
}

# Agentes que no hacen RAG y deben excluirse del conteo rag_empty.
_NO_RAG_AGENTS = frozenset({"publicador", "formateador"})


def _por_articulo(pasos) -> dict:
    """Agrupa pasos por artículo conservando el orden en que vienen.

    `group_executions` parte una secuencia **de un solo artículo**: separa por
    `step_index` volviendo a 0, y mezclar artículos haría que el paso 0 del
    siguiente cortara la ejecución del anterior.
    """
    agrupado: dict = {}
    for paso in pasos:
        agrupado.setdefault(paso.article_id, []).append(paso)
    return agrupado


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
            # `group_executions` separa las pasadas por este campo.
            AgentRunStepModel.step_index,
        ).where(
            and_(
                AgentRunStepModel.project_id == project_id,
                AgentRunStepModel.created_at >= since,
            )
        ).order_by(
            AgentRunStepModel.article_id,
            AgentRunStepModel.created_at,
            AgentRunStepModel.step_index,
        )
    )
    steps = steps_q.all()

    tokens_in = sum(r.tokens_in or 0 for r in steps)
    tokens_out = sum(r.tokens_out or 0 for r in steps)
    latencies = [r.latency_ms for r in steps if r.latency_ms]
    latency_p50 = statistics.median(latencies) if latencies else 0.0
    articles_analyzed = len({r.article_id for r in steps if r.article_id})

    # -- ejecuciones del pipeline en la ventana ----------------------------------
    # Contar filas de `agent_runs` daba el número de **pasos**, no de ejecuciones:
    # `log_run_start` mina un run_id por paso. Lo que separa dos pasadas es que
    # `step_index` vuelve a 0, que es el criterio de `group_executions`.
    executions_total = sum(
        len(group_executions(pasos)) for pasos in _por_articulo(steps).values()
    )

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

    # -- consumo acumulado por agente -------------------------------------------
    # Se agrega aquí y no en el cliente: la fila de agent_run_steps ya trae el
    # agente, sus tokens y su latencia, y el cliente solo recibe el resumen.
    por_agente: dict[str, dict] = {}
    for r in steps:
        ag = por_agente.setdefault(r.agent_name, {
            "name": r.agent_name,
            "runs": 0, "tokens_in": 0, "tokens_out": 0,
            "latency_ms": 0.0, "errors": 0,
        })
        ag["runs"] += 1
        ag["tokens_in"] += r.tokens_in or 0
        ag["tokens_out"] += r.tokens_out or 0
        ag["latency_ms"] += r.latency_ms or 0.0
        if r.status not in _completed and r.status != "running":
            ag["errors"] += 1
    for ag in por_agente.values():
        ag["tokens_total"] = ag["tokens_in"] + ag["tokens_out"]
        ag["latency_ms"] = round(ag["latency_ms"], 1)

    return {
        "window_days": WINDOW_DAYS,
        "by_agent": sorted(por_agente.values(), key=lambda a: a["name"]),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens_total": tokens_in + tokens_out,
        "latency_p50_ms": round(latency_p50, 1),
        "articles_analyzed": articles_analyzed,
        "executions_total": executions_total,
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


async def project_swarm_state(session: AsyncSession, project_id: UUID) -> dict:
    """Estado de cada agente del proyecto, derivado de hechos (SPEC-028 / T16.4 / AC4).

    **Se deriva, no se almacena.** Un registro de estado vivo sería un segundo
    sitio donde la verdad puede quedar desincronizada. El hecho es la fila de
    ``agent_runs``: ``log_run_start`` la abre con ``status='running'`` y
    ``log_run_end`` la cierra. Un paso abierto es una fila que nadie cerró.

    No se mira ``agent_run_steps`` —que es lo que sugería la spec— porque el
    orquestador escribe esa traza **al cerrar** el nodo: mientras un agente está
    trabajando todavía no tiene fila ahí, que es justo el momento que AC4 quiere
    ver.

    El umbral existe porque un proceso que muere deja el paso abierto para
    siempre. Pasado ``SWARM_STALE_AFTER_S`` el agente no se muestra como
    «ejecutando» sino como «incierto»: sin el umbral la portada mentiría en el
    caso justo en que más importa.
    """
    ahora = datetime.now(timezone.utc)
    since = ahora - timedelta(days=WINDOW_DAYS)

    # Pasos abiertos del proyecto. `agent_runs` no lleva project_id, así que se
    # acota por el artículo: un run abierto puede no tener aún fila en
    # agent_run_steps, de modo que no sirve cruzarlo por ahí.
    abiertos_q = await session.execute(
        select(AgentRunModel.agent_name, AgentRunModel.started_at)
        .join(ArticleModel, AgentRunModel.article_id == ArticleModel.id)
        .where(
            and_(
                ArticleModel.project_id == project_id,
                AgentRunModel.status == "running",
                AgentRunModel.finished_at.is_(None),
            )
        )
    )
    abiertos: dict[str, list[datetime]] = {}
    for nombre, inicio in abiertos_q.all():
        abiertos.setdefault(nombre, []).append(inicio)

    perfiles_q = await session.execute(
        select(AgentProfileModel.slug, AgentProfileModel.name)
        .where(AgentProfileModel.project_id == project_id)
    )
    perfiles = {slug: nombre for slug, nombre in perfiles_q.all()}

    # Agentes vistos en la traza reciente: si uno perdió su perfil, sigue siendo
    # parte de lo que el proyecto ejecutó y callarlo esconde el descuadre.
    vistos_q = await session.execute(
        select(AgentRunStepModel.agent_name)
        .where(
            and_(
                AgentRunStepModel.project_id == project_id,
                AgentRunStepModel.created_at >= since,
            )
        ).distinct()
    )
    vistos = {fila[0] for fila in vistos_q.all()}

    agentes = []
    for slug in sorted(set(perfiles) | vistos | set(abiertos)):
        inicios = abiertos.get(slug, [])
        # El más antiguo: si hay dos pasos abiertos, el que decide si esto lleva
        # colgado demasiado tiempo es el que lleva más esperando.
        desde = min(inicios) if inicios else None
        if desde is not None and desde.tzinfo is None:
            desde = desde.replace(tzinfo=timezone.utc)

        if slug not in perfiles:
            estado = "no_configurado"
        elif desde is None:
            estado = "disponible"
        elif (ahora - desde).total_seconds() > SWARM_STALE_AFTER_S:
            estado = "incierto"
        else:
            estado = "ejecutando"

        agentes.append({
            "name": slug,
            "label": perfiles.get(slug) or slug,
            "state": estado,
            "open_steps": len(inicios),
            "since": desde.isoformat() if desde else None,
            "criterion": SWARM_CRITERIA[estado],
        })

    return {
        "stale_after_s": SWARM_STALE_AFTER_S,
        "criteria": SWARM_CRITERIA,
        "agents": agentes,
    }


async def project_executions(session: AsyncSession, project_id: UUID) -> list[dict]:
    """Las ejecuciones del proyecto, una por pasada del pipeline (SPEC-029 / T17.1 / AC1).

    Un artículo reejecutado tiene varias pasadas en la misma tabla, y agregarlas
    en una sola fila —que es lo que hace ``project_articles_summary``— esconde
    justamente lo que AC1 pide ver. Aquí cada pasada es su propia fila, con sus
    pasos, su estado y su coste.

    La separación la decide ``group_executions``: dos pasadas se distinguen porque
    ``step_index`` vuelve a 0. **No** se agrupa por ``run_id``, que se mina por
    paso y no por ejecución, ni por ``correlation_id``, que puede faltar.
    """
    since = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)

    rows = (await session.execute(
        select(AgentRunStepModel).where(
            and_(
                AgentRunStepModel.project_id == project_id,
                AgentRunStepModel.created_at >= since,
            )
        ).order_by(
            AgentRunStepModel.article_id,
            AgentRunStepModel.created_at,
            AgentRunStepModel.step_index,
        )
    )).scalars().all()

    ejecuciones: list[dict] = []
    for article_id, pasos in _por_articulo(rows).items():
        grupos = group_executions(pasos)
        for numero, grupo in enumerate(grupos, start=1):
            por_agente: dict[str, dict] = {}
            for p in grupo:
                ag = por_agente.setdefault(p.agent_name, {
                    "name": p.agent_name,
                    "runs": 0, "tokens_in": 0, "tokens_out": 0,
                    "latency_ms": 0.0, "errors": 0,
                })
                ag["runs"] += 1
                ag["tokens_in"] += p.tokens_in or 0
                ag["tokens_out"] += p.tokens_out or 0
                ag["latency_ms"] += p.latency_ms or 0.0
                if p.status not in {"completed", "running"}:
                    ag["errors"] += 1
            for ag in por_agente.values():
                ag["tokens_total"] = ag["tokens_in"] + ag["tokens_out"]
                ag["latency_ms"] = round(ag["latency_ms"], 1)

            tokens_in = sum(p.tokens_in or 0 for p in grupo)
            tokens_out = sum(p.tokens_out or 0 for p in grupo)
            fallidos = [p for p in grupo if p.status not in {"completed", "running"}]
            ejecutando = any(p.status == "running" for p in grupo)

            ejecuciones.append({
                # Estable entre peticiones: sirve de clave en la tabla del cliente.
                "execution_id": f"{article_id}:{numero}",
                "article_id": str(article_id),
                #: Qué pasada es, y de cuántas: «2 de 3» es lo que distingue una
                #: reejecución de un retroceso inexplicado.
                "run_number": numero,
                "runs_total": len(grupos),
                "started_at": grupo[0].created_at,
                "ended_at": grupo[-1].created_at,
                "steps": len(grupo),
                # Orden de aparición, que es el del pipeline, no alfabético.
                "agents_run": list(dict.fromkeys(p.agent_name for p in grupo)),
                "agents": sorted(por_agente.values(), key=lambda a: a["name"]),
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "tokens_total": tokens_in + tokens_out,
                "latency_ms": round(sum(p.latency_ms or 0.0 for p in grupo), 1),
                #: Vueltas del bucle revisor→redactor (0 = aprobado a la primera).
                "loops": max((p.iteration or 0) for p in grupo),
                "failed": bool(fallidos),
                "status": "failed" if fallidos else ("running" if ejecutando else "completed"),
            })

    # La más reciente primero: es la que explica el texto actual del artículo.
    ejecuciones.sort(key=lambda e: e["started_at"], reverse=True)
    return ejecuciones


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
        art = by_article.setdefault(aid, {
            "article_id": str(aid),
            "tokens_in": 0,
            "tokens_out": 0,
            "latency_ms": 0.0,
            "agents_run": set(),
            # Desglose por agente: lo que la fila desplegable de la tabla enseña.
            "agents": {},
            "failed": False,
            "last_run": None,
        })
        art["tokens_in"] += r.tokens_in or 0
        art["tokens_out"] += r.tokens_out or 0
        art["latency_ms"] += r.latency_ms or 0.0
        art["agents_run"].add(r.agent_name)
        fallo = r.status not in {"completed", "running"}
        if fallo:
            art["failed"] = True
        art["last_run"] = r.created_at

        ag = art["agents"].setdefault(r.agent_name, {
            "name": r.agent_name,
            "runs": 0, "tokens_in": 0, "tokens_out": 0,
            "latency_ms": 0.0, "errors": 0,
        })
        ag["runs"] += 1
        ag["tokens_in"] += r.tokens_in or 0
        ag["tokens_out"] += r.tokens_out or 0
        ag["latency_ms"] += r.latency_ms or 0.0
        if fallo:
            ag["errors"] += 1

    result = []
    for item in by_article.values():
        item["agents_run"] = sorted(item["agents_run"])
        item["tokens_total"] = item["tokens_in"] + item["tokens_out"]
        item["latency_ms"] = round(item["latency_ms"], 1)
        for ag in item["agents"].values():
            ag["tokens_total"] = ag["tokens_in"] + ag["tokens_out"]
            ag["latency_ms"] = round(ag["latency_ms"], 1)
        item["agents"] = sorted(item["agents"].values(), key=lambda a: a["name"])
        result.append(item)
    return result
