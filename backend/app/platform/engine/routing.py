"""Enrutado del grafo **como datos** (SPEC-013 / T8.3 / ADR-0005).

Antes, el bucle de revisión estaba escrito en el código del orquestador: la
condición miraba `if node_name == "revisor"`, el destino del rechazo era la
cadena `"redactor"`, y el umbral y el máximo de vueltas eran constantes de módulo.
Eso funciona mientras el único proyecto sea AlejandrIA. En una plataforma donde
cada proyecto trae sus propios agentes, un revisor que se llame `qa` o `editor`
no tiene bucle, y nadie se entera: el grafo se compila igual y el flujo
simplemente sigue recto.

Aquí el bucle es un **dato** (`ReviewLoop`) y el enrutador se fabrica a partir de
él, así que un proyecto puede declarar el suyo —o ninguno— sin tocar el motor.
T8.4 lo leerá del `template.yaml`; de momento lo declara el proyecto en Python.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Sequence, Tuple

logger = logging.getLogger(__name__)

FIN = "__end__"

#: Decisiones que una persona puede tomar de forma explícita en una pausa (SPEC-036/AC9).
EXPLICIT_DECISIONS = ("add_source", "continue")
#: Desenlace de una pausa que nadie respondió. No es una decisión: el enrutador la ignora y
#: sigue por la puntuación y las vueltas, así que jamás salta la revisión.
NO_RESPONSE = "no_response"


@dataclass(frozen=True)
class ReviewLoop:
    """Un nodo que evalúa y puede devolver el flujo a un nodo anterior.

    Attributes:
        reviewer: nodo que emite la evaluación.
        on_reject: nodo al que se vuelve cuando la evaluación no llega al umbral.
        threshold: puntuación mínima para avanzar (`approval_score` del estado).
        max_loops: vueltas automáticas antes de avanzar de todos modos. Sin este
            tope, un revisor severo deja el pipeline dando vueltas para siempre.
        retry_targets: candidatos, en orden, a los que volver cuando la persona
            usuaria decide **añadir una fuente**. Se elige el primero que esté en
            el flujo; si no hay ninguno, se avanza.
        on_exhausted: qué pasa al agotar las vueltas con la revisión sin aprobar.
            `advance` (por defecto) sigue al nodo siguiente de todos modos;
            `stop` termina la ejecución ahí y deja la decisión a una persona
            (SPEC-032/AC7): publicar lo que el revisor no aprobó es justo lo que
            esa regla evita.
    """

    reviewer: str
    on_reject: str
    threshold: float = 80.0
    max_loops: int = 3
    retry_targets: Tuple[str, ...] = field(default_factory=tuple)
    on_exhausted: str = "advance"


def make_halt_router(siguiente: str) -> Callable[[Dict[str, Any]], str]:
    """Arista de un nodo sin bucle: sigue al `siguiente`, salvo que el nodo se haya abstenido.

    `abstained` en el estado termina la ejecución en ese punto, igual que `on_exhausted: stop`
    lo hace con la revisión. Quien se abstiene deja dicho el porqué en `abstention`.
    """

    def router(state: Dict[str, Any]) -> str:
        if state.get("abstained"):
            logger.info("Un nodo se abstuvo: se detiene el flujo antes de '%s'.", siguiente)
            return FIN
        return siguiente

    return router


def next_after(flow: Sequence[str], node: str) -> str:
    """Nodo que sigue a `node` en el flujo, o el final."""
    try:
        indice = list(flow).index(node)
    except ValueError:
        return FIN
    if indice + 1 < len(flow):
        return flow[indice + 1]
    return FIN


def needs_rework(loop: ReviewLoop, state: Dict[str, Any]) -> bool:
    """¿La revisión no aprueba? Puntuación bajo el umbral o `coherent` falso."""
    return state.get("approval_score", 100) < loop.threshold or state.get("coherent") is False


def review_exhausted(loop: ReviewLoop, state: Dict[str, Any]) -> bool:
    """Se agotaron las vueltas y la revisión sigue sin aprobar, y nadie decidió seguir.

    Una decisión humana de continuar manda sobre la revisión automática.
    """
    if state.get("user_decision") == "continue":
        return False
    return needs_rework(loop, state) and state.get("loop_count", 0) >= loop.max_loops


def make_review_router(loop: ReviewLoop) -> Callable[[Dict[str, Any]], str]:
    """Construye la arista condicional que sale de `loop.reviewer`.

    Tres caminos, en este orden de precedencia:

    1. **Decisión humana** (`user_decision`). Manda sobre la puntuación: si
       alguien ha mirado el borrador y ha dicho qué hacer, el umbral automático
       ya no tiene voz.
    2. **Puntuación por debajo del umbral** y quedan vueltas → se vuelve a
       `on_reject`.
    3. En cualquier otro caso, el siguiente nodo del flujo.
    """

    def router(state: Dict[str, Any]) -> str:
        flow = list(state.get("flow_sequence") or [])
        decision = state.get("user_decision")
        # Solo una decisión explícita manda sobre la revisión; cualquier otro valor
        # (p. ej. «no_response») equivale a que nadie decidió (SPEC-036/AC9).
        if decision not in EXPLICIT_DECISIONS:
            decision = None

        if state.get("abstained"):
            return FIN

        if decision == "add_source":
            for candidato in loop.retry_targets:
                if candidato in flow:
                    logger.info(
                        "Se añadió una fuente — volviendo a '%s' desde '%s'.",
                        candidato, loop.reviewer,
                    )
                    return candidato
            return next_after(flow, loop.reviewer)

        if decision == "continue":
            logger.info("Continuar con el borrador actual (decisión humana).")
            return next_after(flow, loop.reviewer)

        score = state.get("approval_score", 100)
        vueltas = state.get("loop_count", 0)
        if needs_rework(loop, state) and vueltas < loop.max_loops:
            logger.info(
                "'%s' puntuó %s (vuelta %s/%s). Volviendo a '%s'.",
                loop.reviewer, score, vueltas, loop.max_loops, loop.on_reject,
            )
            return loop.on_reject

        if loop.on_exhausted == "stop" and review_exhausted(loop, state):
            logger.info(
                "'%s' agotó %s vueltas sin aprobar (puntuación %s). Se detiene para revisión humana.",
                loop.reviewer, loop.max_loops, score,
            )
            return FIN

        siguiente = next_after(flow, loop.reviewer)
        logger.info("'%s' puntuó %s. Avanzando a '%s'.", loop.reviewer, score, siguiente)
        return siguiente

    return router
