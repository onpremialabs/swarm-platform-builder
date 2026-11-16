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

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, Sequence, Tuple

from langgraph.graph import END, START, StateGraph

from app.platform.engine.routing import FIN, ReviewLoop, make_review_router


class UnknownAgent(ValueError):
    """El flujo nombra un agente que nadie sabe ejecutar."""


class InvalidVariant(ValueError):
    """La selección de agentes no produce un flujo que se pueda ejecutar.

    Se lanza **antes** de arrancar. El error que esto evita es el que T8.4 ya
    evitó al cargar el proyecto: descubrir en el minuto ocho que el bucle de
    revisión apunta a un nodo que no está.
    """


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


def restrict_to(spec: GraphSpec, seleccion: Sequence[str]) -> GraphSpec:
    """Variante del `GraphSpec` acotada a los agentes seleccionados (T18.2 / AC2).

    Se construye **a partir del spec del proyecto**, no en paralelo: el resultado
    es otro `GraphSpec` que pasa por las mismas comprobaciones, así que la
    validación no se duplica y no puede divergir.

    Qué se rechaza, y por qué:

    * Un agente que el proyecto no declara. Es el mismo error que
      `'graph.sequence' nombra a X, que no está declarado en 'agents'`, solo que
      ahora llega por la petición en vez de por el YAML.
    * Una selección vacía: un flujo sin nodos no ejecuta nada.
    * **Un revisor cuyo destino de rechazo se ha quitado.** Es el caso que da
      nombre al AC, y el más traicionero: `GraphSpec.nodes()` vuelve a añadir el
      destino del bucle aunque no esté en la secuencia —hace falta para que la
      arista condicional no apunte al vacío—, así que el agente excluido se
      ejecutaría igual. Quien pidió no ejecutarlo tiene derecho a que se le diga
      que eso no se puede, en vez de a que se le ignore en silencio.

    El orden lo pone el **proyecto**, no el cliente: la secuencia es el flujo
    editorial, y dejar que la petición lo reordene convertiría un selector de
    participantes en un editor de pipeline, que es trabajo del Flow Designer.
    """
    pedidos = [str(n).strip() for n in seleccion if str(n).strip()]
    if not pedidos:
        raise InvalidVariant("No se ha seleccionado ningún agente: el flujo quedaría vacío")

    conocidos = set(spec.nodes())
    desconocidos = [n for n in pedidos if n not in conocidos]
    if desconocidos:
        raise InvalidVariant(
            "El proyecto no declara estos agentes: "
            + ", ".join(sorted(set(desconocidos)))
        )

    elegidos = set(pedidos)
    secuencia = tuple(n for n in spec.sequence if n in elegidos)
    if not secuencia:
        raise InvalidVariant(
            "Ninguno de los agentes seleccionados está en la secuencia del proyecto"
        )

    bucles = []
    for loop in spec.loops:
        if loop.reviewer not in elegidos:
            # El revisor no participa: su bucle se va con él. No es un error,
            # es lo que significa quitar al revisor.
            continue
        if loop.on_reject not in elegidos:
            raise InvalidVariant(
                f"'{loop.reviewer}' rechaza hacia '{loop.on_reject}', que has "
                f"quitado de la selección. O incluyes '{loop.on_reject}', o "
                f"quitas también '{loop.reviewer}': si no, el bucle lo ejecutaría "
                f"igual y tu exclusión no serviría de nada."
            )
        # Los destinos de reintento son preferencias —la plantilla documenta que
        # cae al siguiente si uno no está en el flujo—, así que se filtran.
        bucles.append(replace(
            loop,
            retry_targets=tuple(d for d in loop.retry_targets if d in elegidos),
        ))

    # Construir el GraphSpec es la validación: su __post_init__ rechaza lo vacío.
    return GraphSpec(sequence=secuencia, loops=tuple(bucles))


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
            workflow.add_edge(nombre, spec.sequence[indice + 1])

    return workflow.compile(checkpointer=checkpointer)
