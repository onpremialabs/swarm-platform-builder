"""Construcción del grafo a partir de una especificación (SPEC-013 / T8.3).

`Orchestrator.compile_graph` conocía a AlejandrIA de tres formas distintas: un
`dict` con los cinco agentes por nombre, un `if "revisor" in nodes: add("redactor")`
para asegurar el destino del bucle, y un `if node_name == "revisor"` para colocar
la arista condicional. Con eso, un proyecto con otros agentes compila un grafo
recto sin bucle y sin avisar.

Aquí el grafo se construye desde un `GraphSpec` —la secuencia y los bucles— y una
función que resuelve nombres a ejecutables. El motor no sabe qué agentes existen;
eso lo aporta el proyecto, que es exactamente lo que T8.4 leerá del `template.yaml`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Sequence, Tuple

from langgraph.graph import END, START, StateGraph

from app.platform.engine.routing import FIN, ReviewLoop, make_halt_router, make_review_router


class UnknownAgent(ValueError):
    """El flujo nombra un agente que nadie sabe ejecutar."""


@dataclass(frozen=True)
class GraphSpec:
    """Forma del pipeline de un proyecto: qué nodos, en qué orden, con qué bucles."""

    sequence: Tuple[str, ...]
    loops: Tuple[ReviewLoop, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.sequence:
            raise ValueError("La secuencia del flujo no puede estar vacía")

    def loop_for(self, node: str) -> ReviewLoop | None:
        for loop in self.loops:
            if loop.reviewer == node:
                return loop
        return None

    def active_loops(self) -> Tuple[ReviewLoop, ...]:
        """Solo los bucles cuyo revisor está de verdad en este flujo."""
        return tuple(loop for loop in self.loops if loop.reviewer in self.sequence)

    def nodes(self) -> Tuple[str, ...]:
        """Nodos a registrar: los del flujo más los destinos de los bucles activos.

        El destino de un bucle puede no estar en la secuencia —ejecutar solo
        `revisor` sigue necesitando `redactor` para poder rechazar—, así que hay
        que registrarlo igual o la arista condicional apuntaría a un nodo que no
        existe. Antes esto era una línea escrita a mano para el par
        revisor→redactor; ahora sale de los datos.
        """
        vistos: list[str] = list(self.sequence)
        for loop in self.active_loops():
            for extra in (loop.on_reject, *loop.retry_targets):
                if extra and extra not in vistos:
                    vistos.append(extra)
        return tuple(vistos)


def build_graph(
    spec: GraphSpec,
    node_factory: Callable[[str], Any],
    state_type: Any,
    checkpointer: Any = None,
) -> Any:
    """Compila el `StateGraph` descrito por `spec`.

    Args:
        spec: forma del pipeline.
        node_factory: nombre → función asíncrona de nodo. Lanza `UnknownAgent` si
            no sabe resolverlo.
        state_type: el `TypedDict` del estado compartido.
        checkpointer: persistencia de LangGraph, para poder reanudar.
    """
    workflow = StateGraph(state_type)

    for nombre in spec.nodes():
        workflow.add_node(nombre, node_factory(nombre))

    workflow.add_edge(START, spec.sequence[0])

    for indice, nombre in enumerate(spec.sequence):
        loop = spec.loop_for(nombre)
        if loop is not None:
            # El mapa de destinos tiene que contener **todos** los nodos a los que
            # el enrutador puede devolver, incluidos los de reintento que no están
            # en la secuencia.
            destinos: Dict[str, Any] = {FIN: END}
            for destino in (*spec.sequence, loop.on_reject, *loop.retry_targets):
                if destino:
                    destinos[destino] = destino
            workflow.add_conditional_edges(nombre, make_review_router(loop), destinos)
        elif indice == len(spec.sequence) - 1:
            workflow.add_edge(nombre, END)
        else:
            # Un nodo que se abstiene (`abstained`, SPEC-034/AC7) detiene el flujo: lo que
            # sigue se apoyaría en una investigación que no existe. El motor no sabe quién
            # se abstiene ni por qué; solo respeta la marca.
            siguiente = spec.sequence[indice + 1]
            workflow.add_conditional_edges(
                nombre, make_halt_router(siguiente), {FIN: END, siguiente: siguiente},
            )

    return workflow.compile(checkpointer=checkpointer)
