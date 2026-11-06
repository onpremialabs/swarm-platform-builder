import asyncio
import logging
import datetime
import re
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional

from sqlalchemy import select, update
from langgraph.checkpoint.memory import InMemorySaver

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging_config import request_id_ctx
from app.platform import explainability
from app.platform.run_lifecycle import runtime_owner, OWNER_KEY
from app.platform.llm import TransientLLMError, resolve_agent_model
from app.platform.project_context import ProjectContext
from app.models import AgentRunModel, AgentRunStepModel, ArticleModel, ArticleStatus
from app.modules.agents.domain.entities import AgentState
from app.modules.agents.domain import alejandria
from app.platform.engine.agents import MODO_CAPACIDADES, bundle_for, resolve_runner, uses_llm
from app.platform.capabilities.binding import CLAVE_ESTADO as CLAVE_CAPACIDADES
from app.platform.engine.graph import GraphSpec, build_graph
from app.platform.engine.routing import make_review_router, next_after, review_exhausted
from app.modules.agents.adapters.generic import run_generic_agent, load_agent_profile
from app.platform.bus import get_bus
from app.platform.metrics import current_agent_ctx, observe_agent_run
from app.platform.tracing import record_error, span

logger = logging.getLogger(__name__)

# Registro de tareas del pipeline: article_id -> asyncio.Task.
#
# **Sigue siendo local al worker** y no puede dejar de serlo: un `asyncio.Task` es
# el manejador de una corrutina viva, no un dato serializable. Lo que sí cruza
# procesos es la *señal* de cancelación, que viaja por el bus (SPEC-018/T4.3): el
# worker dueño de la tarea registra un handler y la cancela cuando llega.
active_tasks: Dict[uuid.UUID, asyncio.Task] = {}

# LangGraph checkpointer: persists the graph state after every completed node so a
# failed pipeline can be resumed from the last successful step instead of restarting.
# Keyed by thread_id == str(article_id). In-memory: survives transient agent errors
# (e.g. Ollama momentarily unreachable) while the backend process keeps running.
#
# **Sigue siendo por proceso, también con Redis (T4.3).** El bus comparte eventos,
# decisiones y tickets, pero no esto: si una reanudación cae en un worker distinto
# del que guardó el checkpoint, no lo encuentra y el pipeline empieza de cero. Para
# que `resume` funcione entre workers hace falta un saver compartido
# (`langgraph-checkpoint-redis` o el de Postgres), que es cambio aparte.
_pipeline_checkpointer = InMemorySaver()


def _thread_config(article_id: uuid.UUID) -> Dict[str, Any]:
    """Build the LangGraph config that scopes checkpoints to a single article run."""
    return {"configurable": {"thread_id": str(article_id)}}


async def has_pipeline_checkpoint(article_id: uuid.UUID) -> bool:
    """Return True if a resumable checkpoint exists for this article's pipeline."""
    try:
        tuple_ = await _pipeline_checkpointer.aget_tuple(_thread_config(article_id))
        return tuple_ is not None
    except Exception:
        return False

# Default decision when the user does not respond in time (avoid hanging forever)
_DECISION_TIMEOUT = 900.0  # 15 minutes


async def request_user_decision(article_id: uuid.UUID, payload: Dict[str, Any]) -> str:
    """Pause the pipeline and ask the user for a decision.

    Emits an ``await_decision`` SSE event and blocks until the user responds via
    ``submit_user_decision`` or the timeout elapses (defaulting to "continue").
    """
    bus = get_bus()
    async with bus.awaiting_decision(article_id) as future:
        publish_event(article_id, {"type": "await_decision", **payload})
        try:
            return await asyncio.wait_for(future, timeout=_DECISION_TIMEOUT)
        except asyncio.TimeoutError:
            logger.info("User decision timed out for article %s — defaulting to 'continue'", article_id)
            publish_event(article_id, {"type": "decision_resolved", "decision": "continue", "timed_out": True})
            return "continue"


async def submit_user_decision(article_id: uuid.UUID, decision: str) -> bool:
    """Entregar una decisión pendiente. `True` si había alguien esperándola.

    Puede resolverla un worker distinto del que ejecuta el pipeline: el bus lleva el
    valor hasta el `Future` que espera, esté donde esté (SPEC-018/T4.3).
    """
    entregada = await get_bus().submit_decision(article_id, decision)
    if entregada:
        publish_event(article_id, {"type": "decision_resolved", "decision": decision})
    return entregada

# In-memory log buffer: article_id -> list of formatted log lines
_log_buffers: Dict[uuid.UUID, List[str]] = {}

# Logs output directory (relative to CWD, i.e. backend/)
_LOGS_DIR = Path("logs")


def _sanitize_filename(text: str) -> str:
    """Convert arbitrary text to a safe filename component."""
    text = text.strip()
    # Replace spaces and separators with underscores
    text = re.sub(r"[\s/\\:*?\"<>|]+", "_", text)
    # Keep only alphanumeric, underscores, and hyphens
    text = re.sub(r"[^\w\-]", "", text)
    return text[:60] or "pipeline"


def _flush_log_file(article_id: uuid.UUID, title: str) -> None:
    """Write the accumulated log buffer for an article to a file in the logs/ directory."""
    lines = _log_buffers.pop(article_id, [])
    if not lines:
        return
    try:
        _LOGS_DIR.mkdir(parents=True, exist_ok=True)
        date_str = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        safe_title = _sanitize_filename(title)
        filename = _LOGS_DIR / f"log_{safe_title}_{date_str}.txt"
        content = "\n".join(lines)
        filename.write_text(content, encoding="utf-8")
        logger.info("Pipeline log saved to %s", filename)
    except Exception as exc:
        logger.warning("Could not write pipeline log file: %s", exc)


# Generated by GitHub Copilot
def publish_event(article_id: uuid.UUID, event: dict) -> None:
    """Push an SSE event dict to all queues subscribed to the given article_id.
    Log-type events are also appended to the in-memory buffer for file persistence.
    """
    # Buffer log lines for file output
    ev_type = event.get("type")
    if ev_type == "log":
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        agent = event.get("agent", "pipeline")
        msg = event.get("message", "")
        level = (event.get("level") or "info").upper()
        _log_buffers.setdefault(article_id, []).append(
            f"[{ts}] [{level}] [{agent}] {msg}"
        )
    elif ev_type == "agent_error":
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        agent = event.get("agent", "?")
        err = event.get("error", "")
        _log_buffers.setdefault(article_id, []).append(
            f"[{ts}] [ERROR] [{agent}] ✗ {err}"
        )

    # El bus decide si esto es entrega en proceso o un pub/sub que llega a todos
    # los workers (SPEC-018/T4.3). Sigue siendo síncrono porque los agentes emiten
    # tokens desde callbacks que no pueden hacer await.
    get_bus().publish_nowait(article_id, event)


async def log_run_start(
    agent_name: str,
    article_id: uuid.UUID,
    author_id: uuid.UUID,
    input_payload: dict,
) -> uuid.UUID:
    """Persist an AgentRun record with status 'running' and return its run_id."""
    run_id = uuid.uuid4()
    runtime_owner.tasks[run_id] = asyncio.current_task()
    try:
        owner_metadata = runtime_owner.metadata
        async with AsyncSessionLocal() as session:
            run = AgentRunModel(
                run_id=run_id,
                agent_name=agent_name,
                article_id=article_id,
                author_id=author_id,
                status="running",
                input_payload={**input_payload, OWNER_KEY: owner_metadata},
                started_at=datetime.datetime.now(datetime.timezone.utc),
            )
            session.add(run)
            await session.commit()
            return run_id
    except Exception as e:
        logger.error(f"Error logging run start for {agent_name}: {str(e)}")
        # A commit error can have an uncertain outcome: retain ownership until
        # completion so reconciliation cannot close an agent still working.
        return run_id


async def log_run_end(
    run_id: uuid.UUID,
    output_payload: dict,
    status: str,
    error_message: str = None,
) -> None:
    """Update an existing AgentRun record with the final status and output."""
    runtime_owner.terminal_results[run_id] = {"output_payload": output_payload or {},
        "status": status, "error_message": error_message}
    for attempt in range(3):
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(update(AgentRunModel).where(
                    AgentRunModel.run_id == run_id,
                    AgentRunModel.status == "running",
                    AgentRunModel.finished_at.is_(None),
                ).values(output_payload=output_payload or {}, status=status,
                    error_message=error_message,
                    finished_at=datetime.datetime.now(datetime.timezone.utc)))
                await session.commit()
            runtime_owner.tasks.pop(run_id, None)
            runtime_owner.terminal_results.pop(run_id, None)
            return
        except Exception:
            if attempt < 2:
                await asyncio.sleep(0.1 * (attempt + 1))
            else:
                logger.exception("Could not close run %s; lifecycle monitor will reconcile it", run_id)


async def _hash_anterior(session, article_id, step_index: int) -> str | None:
    """Hash del paso anterior de la **misma** ejecución (SPEC-029 / T17.2 / AC4).

    `step_index == 0` abre ejecución —el mismo criterio que `group_executions`—,
    así que ancla en vez de enlazar con la ejecución previa del artículo. Una
    reanudación no reinicia el índice y por tanto continúa la cadena, que es
    justo lo que AC7 pide para no dar falso positivo.
    """
    if step_index == 0 or article_id is None:
        return None
    fila = (await session.execute(
        select(AgentRunStepModel.content_hash)
        .where(AgentRunStepModel.article_id == article_id)
        .order_by(AgentRunStepModel.created_at.desc(),
                  AgentRunStepModel.step_index.desc())
        .limit(1)
    )).first()
    return fila[0] if fila else None


async def close_orphan_runs() -> int:
    """Cierra los pasos que quedaron abiertos de un arranque anterior.

    Una cancelación o un fallo cierran su fila desde dentro. Lo que no puede
    cerrarse desde dentro es un proceso que muere de golpe —`SIGKILL`, un corte de
    luz, cerrar la ventana— y esas filas se quedan en `running` para siempre,
    haciendo que el agente aparezca como «incierto» indefinidamente (T16.4).

    Se llama al arrancar: si este proceso acaba de empezar, nada de lo que dejó
    abierto el anterior sigue vivo.

    **Con varios workers esto no es cierto**, así que solo se cierran las filas
    más antiguas que `SWARM_STALE_AFTER_S` —el mismo umbral con el que la portada
    ya deja de llamarlas «ejecutando»—. Una ejecución legítima más larga que eso
    se marcaría por error; a cambio, lo que de verdad murió deja de mentir. El
    umbral es el mismo a propósito: dos criterios distintos para la misma pregunta
    acabarían discrepando.
    """
    from app.platform.summary import SWARM_STALE_AFTER_S

    corte = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        seconds=SWARM_STALE_AFTER_S)
    try:
        async with AsyncSessionLocal() as session:
            huerfanas = (await session.execute(
                select(AgentRunModel).where(
                    AgentRunModel.status == "running",
                    AgentRunModel.finished_at.is_(None),
                    AgentRunModel.started_at < corte,
                )
            )).scalars().all()

            for fila in huerfanas:
                fila.status = "interrupted"
                fila.error_message = (
                    "El proceso terminó sin cerrar este paso; se cerró al arrancar."
                )
                fila.finished_at = datetime.datetime.now(datetime.timezone.utc)
                session.add(fila)

            if huerfanas:
                await session.commit()
                logger.warning(
                    "Cerrados %d paso(s) que quedaron abiertos de un arranque anterior",
                    len(huerfanas),
                    extra={"event": "orphan_runs_closed", "count": len(huerfanas)},
                )
            return len(huerfanas)
    except Exception:
        # Limpiar no puede impedir arrancar: como mucho se queda un «incierto»,
        # que es lo que había antes de esta función.
        logger.warning("No se pudieron cerrar los pasos huérfanos", exc_info=True)
        return 0


async def log_run_step(**campos) -> None:
    """Persiste un paso de la traza de explicabilidad (SPEC-014 / T9.1 / AC1).

    Sesión propia y `try/except`: la traza es observabilidad, y un fallo al
    guardarla no puede tumbar el pipeline que describe. Se registra en el log —a
    nivel WARNING, no en silencio— porque una traza que se pierde sin avisar es
    peor que no tenerla: da confianza infundada.

    Aquí se sella también la cadena de integridad (T17.2): al cerrar el paso, que
    es cuando se conoce su contenido. Un proceso posterior que recorriera la tabla
    para hashearla sería un segundo sitio que puede quedarse atrás, y una cadena
    calculada tarde no distingue «nadie lo ha tocado» de «aún no lo he mirado».
    """
    try:
        async with AsyncSessionLocal() as session:
            prev = await _hash_anterior(
                session, campos.get("article_id"), campos.get("step_index") or 0)
            campos["prev_hash"] = prev
            campos["hash_version"] = explainability.CANON_VERSION
            campos["content_hash"] = explainability.compute_hash(campos, prev)
            session.add(AgentRunStepModel(**campos))
            await session.commit()
    except Exception as error:
        logger.warning(
            "No se pudo persistir el paso de traza de '%s': %s",
            campos.get("agent_name"), error,
        )


def make_node_wrapper(agent_name: str, run_fn):
    """
    Return an async LangGraph node function that wraps run_fn with logging,
    SSE event emission, and step-index tracking.
    """
    async def wrapper(state: AgentState) -> Dict[str, Any]:
        article_id = state.get("article_id")
        author_id = state.get("author_id")

        # Etiquetar las llamadas al LLM con el agente en curso (SPEC-019/T5.2).
        # Aquí y no en `call_llm`: este wrapper es el único punto por el que pasan
        # **todos** los agentes, incluidos los dinámicos de `.agent.md`, así que uno
        # nuevo queda etiquetado sin tocar nada.
        _token_agente = current_agent_ctx.set(agent_name)
        _inicio_agente = time.perf_counter()
        _estado_agente = "error"
        # Span por paso de agente (SPEC-019/T5.3/AC3). Cuelga del span del pipeline
        # porque comparten contexto de ejecución, así que la traza sale anidada sin
        # que haya que pasar padres a mano.
        _span_ctx = span(
            f"agent.{agent_name}",
            **{"agent.name": agent_name, "article.id": str(article_id)},
        )
        _span_agente = _span_ctx.__enter__()

        input_data = {
            "title": state.get("title"),
            "keywords": state.get("keywords"),
            "scientific_format": state.get("scientific_format"),
            "current_step_index": state.get("current_step_index", 0),
            "loop_count": state.get("loop_count", 0),
        }

        def log_fn(message: str, level: str = "info") -> None:
            """Emit a detailed SSE log event for this agent's execution."""
            publish_event(article_id, {"type": "log", "agent": agent_name, "message": message, "level": level})

        def emit_token_fn(token: str) -> None:
            """Emit a word-by-word token SSE event for visual typing."""
            publish_event(article_id, {"type": "token", "agent": agent_name, "token": token})

        def emit_progress_fn(current: int, total: int, unit: str = "") -> None:
            """Progreso **fraccional** del agente (SPEC-030 / T18.4 / AC5).

            Lo emite solo quien conoce sus unidades de trabajo de verdad. Quien no
            las conoce no llama a esto, y la interfaz lo muestra indeterminado:
            una barra indeterminada dice «no sé cuánto falta», que es cierto,
            mientras que un porcentaje inventado tiene la precisión de un dato y
            el valor de una suposición.
            """
            if total <= 0 or current < 0:
                return
            publish_event(article_id, {
                "type": "progress", "agent": agent_name,
                "current": min(current, total), "total": total, "unit": unit,
            })

        async def request_decision_fn(payload: Dict[str, Any]) -> str:
            """Pause this node and await a user decision (human-in-the-loop)."""
            return await request_user_decision(article_id, payload)

        publish_event(article_id, {"type": "agent_start", "agent": agent_name})

        run_id = None

        _traza = None
        _acumulador = explainability.StepAccumulator()
        _paso_comun = {
            "run_id": run_id, "article_id": article_id,
            "project_id": state.get("project_id"), "agent_name": agent_name,
            "step_index": state.get("current_step_index", 0),
            "iteration": state.get("loop_count", 0),
        }
        try:
            run_id = await log_run_start(agent_name, article_id, author_id, input_data)
            _paso_comun["run_id"] = run_id
            # Inject log_fn, emit_token_fn and request_decision_fn into state so
            # adapters can emit SSE events and pause for user input.
            enriched_state = dict(state)
            enriched_state["_log"] = log_fn
            enriched_state["_emit_token"] = emit_token_fn
            enriched_state["_emit_progress"] = emit_progress_fn
            enriched_state["_request_decision"] = request_decision_fn
            # La ejecución en curso, para que quien persista un informe lo ligue a ella.
            enriched_state["_run_id"] = run_id

            # Capacidades del agente (SPEC-013/T8.3/AC8). Con el flag en
            # `capabilities` se resuelven desde el registro y el agente las usa en
            # lugar de sus imports; con el flag en `adapters` no se inyecta nada y el
            # agente sigue el camino de siempre. Los dos deben dar el mismo
            # resultado: eso es lo que comprueba el test de paridad.
            if settings.AGENT_ENGINE == MODO_CAPACIDADES:
                bundle = bundle_for(agent_name)
                if bundle is not None:
                    enriched_state[CLAVE_CAPACIDADES] = bundle

            # Acumulador de la traza: la capacidad de RAG y el dispatcher del LLM
            # anotan aquí lo que solo ellos saben (SPEC-014/T9.1).
            _traza = explainability.collecting()
            _acumulador = _traza.__enter__()
            _paso_comun = {
                "run_id": run_id,
                "article_id": article_id,
                "project_id": state.get("project_id"),
                "correlation_id": request_id_ctx.get(),
                "agent_name": agent_name,
                "step_index": state.get("current_step_index", 0),
                "iteration": state.get("loop_count", 0),
                # Sin capacidad de LLM declarada no hay modelo: antes se resolvía uno para
                # todos y la traza decía que el Publicador usaba un modelo (SPEC-032/AC9).
                "model": (
                    resolve_agent_model(agent_name, state.get("agent_settings"))
                    if uses_llm(agent_name) else None
                ),
                "params": explainability.params_of(agent_name, state),
                "input_digest": explainability.input_digest(state),
            }

            res = await run_fn(enriched_state)
            await log_run_end(run_id, res, "completed")
            _estado_agente = "completed"
            await log_run_step(
                **_paso_comun,
                status="completed",
                output_text=explainability.output_text(res),
                rag_sources=_acumulador.rag_sources,
                tokens_in=_acumulador.tokens_in,
                tokens_out=_acumulador.tokens_out,
                latency_ms=(time.perf_counter() - _inicio_agente) * 1000,
                decision=explainability.decision_of(res),
                rationale=explainability.rationale_of(res),
            )

            end_event: Dict[str, Any] = {"type": "agent_end", "agent": agent_name, "output": res}
            if res.get("draft_text"):
                end_event["draft_text"] = res["draft_text"]
            if res.get("formatted_text"):
                end_event["formatted_text"] = res["formatted_text"]

            publish_event(article_id, end_event)

            # SPEC-032/AC14: la compuerta bloqueó; se avisa aparte del fin del agente.
            if res.get("gate_failed"):
                publish_event(article_id, {
                    "type": "gate_failed",
                    "agent": agent_name,
                    "blockers": res.get("gate_blockers", []),
                })

            res["current_step_index"] = state.get("current_step_index", 0) + 1
            return res
        except asyncio.CancelledError:
            # `CancelledError` hereda de `BaseException`, no de `Exception`: el
            # `except` de abajo **no** la ve. Sin esta rama, cancelar una ejecución
            # dejaba su fila de `agent_runs` abierta para siempre, y el estado del
            # enjambre (T16.4) mostraba ese agente como «incierto» indefinidamente.
            # Cancelar es un botón de la interfaz: el caso no era raro, era uno por
            # cada cancelación.
            logger.info("Agente %s cancelado", agent_name)
            _estado_agente = "cancelled"

            async def close_cancelled():
                await log_run_end(run_id, {}, "cancelled", error_message="Pipeline cancelado o backend detenido")
                # La traza registra la cancelación: AC1 de T9.1 pide el paso
                # «cuando termina **o se cancela**», y dónde se cortó es justo lo
                # que se pregunta después.
                await log_run_step(**_paso_comun, status="cancelled",
                    error_message="Pipeline cancelado o backend detenido",
                    rag_sources=_acumulador.rag_sources,
                    tokens_in=_acumulador.tokens_in, tokens_out=_acumulador.tokens_out,
                    latency_ms=(time.perf_counter() - _inicio_agente) * 1000)

            if run_id is not None:
                # `shield` y no un `await` pelado: estamos **dentro** de una tarea
                # ya cancelada, y un await sin proteger se cancelaría a su vez
                # dejando la fila abierta — el mismo fallo que esta rama arregla.
                await asyncio.shield(close_cancelled())
            # Se vuelve a lanzar siempre: tragarse una cancelación deja la tarea
            # viva y es peor que el problema que arregla.
            raise
        except Exception as e:
            _estado_agente = "failed"
            logger.error(f"Error executing agent {agent_name}: {str(e)}")
            await log_run_end(run_id, {}, "failed", error_message=str(e))
            # También se traza el fallo: AC1 pide la traza «cuando termina **o se
            # cancela**», y un paso que revienta es justo el que hay que explicar.
            await log_run_step(
                **_paso_comun,
                status="failed",
                error_message=str(e),
                rag_sources=_acumulador.rag_sources,
                tokens_in=_acumulador.tokens_in,
                tokens_out=_acumulador.tokens_out,
                latency_ms=(time.perf_counter() - _inicio_agente) * 1000,
            )
            record_error(_span_agente, e)
            publish_event(article_id, {"type": "agent_error", "agent": agent_name, "error": str(e)})
            publish_event(article_id, {"type": "log", "agent": agent_name, "message": f"✗ {agent_name} falló: {str(e)}", "level": "error"})
            raise
        finally:
            # This fallback is conditional in SQL: it cannot overwrite a closed
            # success, failure or cancellation with a different terminal status.
            try:
                if run_id in runtime_owner.tasks and run_id not in runtime_owner.terminal_results:
                    await asyncio.shield(log_run_end(run_id, {},
                        _estado_agente if _estado_agente in {"completed", "failed", "cancelled"} else "failed",
                        error_message="Cierre de protección del intento"))
            finally:
                observe_agent_run(agent_name, time.perf_counter() - _inicio_agente, _estado_agente)
                current_agent_ctx.reset(_token_agente)
                if _traza is not None:
                    _traza.__exit__(None, None, None)
                _span_ctx.__exit__(None, None, None)

    return wrapper


#: Compatibilidad: el bucle de revisión es un dato de la plantilla del proyecto
#: (`template.yaml`) y el enrutado lo fabrica el motor. Se mantienen estos nombres
#: porque hay código y tests que los importan, pero delegan.
MAX_REVIEW_LOOPS = alejandria.review_loop().max_loops


def _next_after_revisor(flow: List[str]) -> str:
    """Nodo que sigue al revisor en el flujo, o el final."""
    return next_after(flow, alejandria.review_loop().reviewer)


def route_after_revisor(state: AgentState) -> str:
    """Arista condicional tras el revisor, construida desde el bucle del proyecto."""
    return make_review_router(alejandria.review_loop())(state)


async def _halt_for_human_review(article_id: uuid.UUID, final_state: Dict[str, Any], flow: List[str]) -> bool:
    """Si la ejecución terminó por agotar las vueltas sin aprobar, deja el artículo
    en `requires_human_review` (SPEC-032/AC7). Devuelve si lo hizo.

    El enrutador ya cortó el flujo (`on_exhausted: stop`): ni el Formateador ni el
    Publicador corrieron. Aquí solo se guarda lo que la persona necesita para
    decidir —el último borrador y los comentarios del revisor— y se avisa por SSE.
    Solo una persona sale de este estado: reejecutar (vuelve a `draft`) o rechazar.
    """
    try:
        loop = alejandria.review_loop()
    except LookupError:
        return False
    if loop.on_exhausted != "stop" or loop.reviewer not in flow:
        return False
    # Con `on_exhausted: stop` el enrutador corta el flujo justo al agotarse las
    # vueltas, así que este predicado y el suyo coinciden por construcción.
    if not review_exhausted(loop, final_state):
        return False

    feedback = final_state.get("feedback") or []
    # El feedback se acumula entre vueltas (`operator.add`); un comentario que se
    # repite en cada pasada se muestra una sola vez.
    comentarios = list(dict.fromkeys(
        str(f) for f in (feedback if isinstance(feedback, list) else [feedback])
    ))
    async with AsyncSessionLocal() as session:
        article = (await session.execute(
            select(ArticleModel).where(ArticleModel.id == article_id)
        )).scalars().first()
        if article is None:
            return False
        article.status = ArticleStatus.REQUIRES_HUMAN_REVIEW
        if final_state.get("draft_text"):
            article.body = final_state["draft_text"]
        article.rejection_comment = "\n".join(comentarios) or None
        session.add(article)
        await session.commit()
    publish_event(article_id, {
        "type": "requires_human_review",
        "score": final_state.get("approval_score"),
        "review_status": final_state.get("review_status"),
        "loops": final_state.get("loop_count"),
        "feedback": comentarios,
    })
    logger.info("Article %s requires human review after %s loops", article_id, final_state.get("loop_count"))
    return True


class Orchestrator:
    """Dynamically compiles and executes a LangGraph flow for article generation."""

    @staticmethod
    def _load_dynamic_agent(name: str):
        """Runner de un agente definido por un perfil `.agent.md`, si existe."""
        if load_agent_profile(name) is None:
            return None
        logger.info("Registrando agente dinámico '%s' desde su perfil .agent.md", name)
        return lambda state, _name=name: run_generic_agent(_name, state)

    @staticmethod
    def compile_graph(flow_sequence: List[str]) -> Any:
        """Compila el grafo del flujo pedido (SPEC-013 / T8.3).

        El motor ya no conoce a los agentes ni al bucle de AlejandrIA: la forma
        del pipeline sale de `GraphSpec` y los nodos del registro de agentes. Lo
        que antes eran tres condiciones con el nombre `"revisor"` escrito dentro
        del orquestador es ahora la declaración del proyecto.
        """
        if not flow_sequence:
            raise ValueError("flow_sequence cannot be empty")

        alejandria.register()
        # La secuencia la pide quien lanza el pipeline (puede ser un subconjunto:
        # reejecutar solo revisor+formateador); los bucles los pone la plantilla.
        spec = GraphSpec(sequence=tuple(flow_sequence), loops=alejandria.loops())

        def node_factory(name: str):
            runner = resolve_runner(name, Orchestrator._load_dynamic_agent)
            return make_node_wrapper(name, runner)

        return build_graph(
            spec,
            node_factory=node_factory,
            state_type=AgentState,
            checkpointer=_pipeline_checkpointer,
        )

    @classmethod
    async def run(
        cls,
        article_id: uuid.UUID,
        author_id: uuid.UUID,
        title: str,
        keywords: List[str],
        scientific_format: str,
        flow_sequence: List[str],
        project: Optional[ProjectContext] = None,
        agent_settings: Dict[str, Any] = None,
        context_description: str = "",
        initial_draft_text: str = "",
        article_outline: str = "",
        # Parámetros de la ejecución (SPEC-030 / AC3, AC6, AC7). Con valor por
        # defecto: una llamada que no los pase sigue funcionando igual.
        swarm_notes: str = "",
        reference_doc_id: Optional[str] = None,
        format_mode: str = "rag",
        resume: bool = False,
    ) -> Dict[str, Any]:
        """Execute the compiled LangGraph flow and return the final state.

        When ``resume`` is True, re-invoke the graph from the last persisted
        checkpoint (the node that previously failed) instead of starting over, so
        the work already done by completed agents is preserved.
        """
        compiled_graph = cls.compile_graph(flow_sequence)
        config = _thread_config(article_id)

        # Resume only makes sense if a checkpoint actually exists; otherwise fall
        # back to a clean run so we never hang waiting for non-existent state.
        if resume and not await has_pipeline_checkpoint(article_id):
            logger.warning(
                "Resume requested for article %s but no checkpoint found — starting fresh.",
                article_id,
            )
            resume = False

        if not resume:
            # Clear any stale checkpoint from a previous attempt so a fresh run
            # starts from START instead of resuming an old thread.
            try:
                await _pipeline_checkpointer.adelete_thread(str(article_id))
            except Exception:
                pass

        initial_state = AgentState(
            article_id=article_id,
            author_id=author_id,
            project_id=project.project_id if project else None,
            title=title,
            keywords=keywords,
            research_data="",
            sources=[],
            draft_text=initial_draft_text,
            feedback=[],
            approval_score=100.0,
            formatted_text="",
            scientific_format=scientific_format,
            published_url="",
            metadata={},
            flow_sequence=flow_sequence,
            current_step_index=0,
            loop_count=0,
            agent_settings=agent_settings or {},
            context_description=context_description,
            article_outline=article_outline,
            # Parametros de la ejecucion: los lee quien ejecuta y acaban en la
            # traza via `params_of`, para que dos pasadas se distingan (AC7).
            swarm_notes=swarm_notes,
            reference_doc_id=reference_doc_id,
            format_mode=format_mode,
        )

        verb = "Resuming" if resume else "Starting"
        logger.info(f"{verb} LangGraph run for article {article_id} with sequence {flow_sequence}")

        # Registrar la corrutina como cancelable. La tarea es local a este worker;
        # lo que se comparte por el bus es la marca de «en curso» y el handler que
        # atiende una cancelación pedida desde otro worker (SPEC-018/T4.3).
        bus = get_bus()
        current_task = asyncio.current_task()
        if current_task is not None:
            active_tasks[article_id] = current_task
            bus.register_cancel_handler(article_id, current_task.cancel)
        await bus.mark_running(article_id)
        # Log en vivo del proyecto (SPEC-029 / T17.5 / AC2): sin este vínculo los
        # eventos del artículo no se encaminan a ningún flujo de proyecto. Aquí
        # y no en el endpoint porque es donde se conoce el proyecto de verdad.
        bus.bind_project(article_id, initial_state.get("project_id"))

        # Span raíz de la ejecución (SPEC-019/T5.3/AC3): los de cada agente cuelgan
        # de este, así que la traza enseña dónde se fue el tiempo dentro del
        # pipeline. Se abre a mano —y no con `with`— porque el cuerpo de la
        # ejecución vive en el try/finally que sigue.
        _span_pipeline_ctx = span(
            "pipeline.run",
            **{
                "article.id": str(article_id),
                "pipeline.agents": " → ".join(flow_sequence),
                "pipeline.resumed": resume,
            },
        )
        _span_pipeline = _span_pipeline_ctx.__enter__()

        # Open log buffer for this run
        _log_buffers[article_id] = []
        ts_start = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header_title = "PIPELINE LOG (REANUDADO)" if resume else "PIPELINE LOG"
        _log_buffers[article_id].append(
            f"{'='*60}\n"
            f"{header_title} — {title}\n"
            f"Artículo ID : {article_id}\n"
            f"Inicio      : {ts_start}\n"
            f"Agentes     : {' → '.join(flow_sequence)}\n"
            f"{'='*60}"
        )
        if resume:
            publish_event(article_id, {
                "type": "log", "agent": "pipeline",
                "message": "↻ Reanudando pipeline desde el último checkpoint", "level": "info",
            })

        try:
            # On resume, pass None so LangGraph continues from the checkpoint
            # (re-running the node that failed) rather than re-seeding from START.
            # A transient failure (e.g. Ollama briefly unreachable) that survives the
            # LLM-layer retries is auto-resumed from the last checkpoint a few times
            # before we surface the error for a manual retry.
            from app.core.config import settings
            max_auto = int(getattr(settings, "PIPELINE_AUTO_RESUME_ATTEMPTS", 2) or 0)
            auto_delay = float(getattr(settings, "PIPELINE_AUTO_RESUME_DELAY", 3.0) or 0.0)

            local_resume = resume
            auto_attempt = 0
            while True:
                try:
                    graph_input = None if local_resume else initial_state
                    final_state = await compiled_graph.ainvoke(graph_input, config=config)
                    break
                except asyncio.CancelledError:
                    raise
                except TransientLLMError as exc:
                    can_auto = (
                        auto_attempt < max_auto
                        and await has_pipeline_checkpoint(article_id)
                    )
                    if not can_auto:
                        raise
                    auto_attempt += 1
                    publish_event(article_id, {
                        "type": "log", "agent": "pipeline", "level": "warn",
                        "message": (
                            f"↻ Error transitorio; reanudando automáticamente desde el "
                            f"checkpoint (intento {auto_attempt}/{max_auto}) en {auto_delay:.0f}s…"
                        ),
                    })
                    logger.warning(
                        "Auto-resuming article %s after transient error (attempt %d/%d): %s",
                        article_id, auto_attempt, max_auto, exc,
                    )
                    await asyncio.sleep(auto_delay)
                    local_resume = True  # subsequent attempts continue from checkpoint
            ts_end = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _log_buffers.setdefault(article_id, []).append(
                f"\n{'='*60}\nFIN — {ts_end} — Pipeline completado con éxito\n{'='*60}"
            )
            await _halt_for_human_review(article_id, final_state, flow_sequence)
            publish_event(article_id, {"type": "done"})
            logger.info(f"Completed LangGraph run for article {article_id}")
            _flush_log_file(article_id, title)
            # Run finished cleanly — drop the checkpoint to free memory.
            try:
                await _pipeline_checkpointer.adelete_thread(str(article_id))
            except Exception:
                pass
            return final_state
        except asyncio.CancelledError:
            ts_end = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _log_buffers.setdefault(article_id, []).append(
                f"\n{'='*60}\nCANCELADO — {ts_end} — Pipeline detenido por el usuario\n{'='*60}"
            )
            publish_event(article_id, {"type": "cancelled"})
            logger.info(f"Pipeline cancelled for article {article_id}")
            _flush_log_file(article_id, title)
            # Leave article in DRAFT — no further DB writes needed
            raise
        except Exception as exc:
            ts_end = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _log_buffers.setdefault(article_id, []).append(
                f"\n{'='*60}\nERROR — {ts_end} — {exc}\n{'='*60}"
            )
            # A checkpoint of the last successful node remains, so the run can be
            # resumed from where it broke. Tell the client it may offer "resume".
            can_resume = await has_pipeline_checkpoint(article_id)
            publish_event(article_id, {
                "type": "done_error", "error": str(exc), "can_resume": can_resume,
            })
            logger.error(f"LangGraph run failed for article {article_id}: {exc}")
            record_error(_span_pipeline, exc)
            _flush_log_file(article_id, title)
            raise
        finally:
            active_tasks.pop(article_id, None)
            bus.unregister_cancel_handler(article_id)
            await bus.clear_running(article_id)
            _span_pipeline_ctx.__exit__(None, None, None)
