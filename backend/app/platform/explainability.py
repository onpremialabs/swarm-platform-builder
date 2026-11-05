"""Recolección de la traza de explicabilidad (SPEC-014 / T9.1 / AC1).

AC1 pide, por cada paso de agente: modelo y parámetros, resumen de entrada y
salida, **fuentes RAG citadas** con `doc_id`, `chunk_ids` y score, tokens in/out,
latencia y, cuando aplique, la decisión con su *rationale*.

Tres de esos datos no están donde se escribe el paso:

* Los **tokens** solo los conoce el proveedor del LLM, dentro de `llm.py`, que ni
  siquiera sabe qué agente está corriendo.
* Las **fuentes RAG** solo las conoce la capacidad de RAG, y el agente que la
  llama se queda con el texto ya montado: las citas que acaban en el artículo son
  una elaboración posterior, no lo que se recuperó.
* La **decisión** la produce el agente y viaja en su salida.

Podrían pasarse por parámetro hasta el orquestador, pero eso significa cambiar la
firma de todo lo que hay en medio y, sobre todo, que un agente nuevo no aparezca
en la traza hasta que alguien se acuerde de instrumentarlo. Aquí se recogen con
**variables de contexto**, igual que `current_agent_ctx` para las métricas
(T5.2): quien produce el dato lo anota donde está, y el orquestador lo recoge al
cerrar el paso. Un agente nuevo queda trazado sin tocarlo.

Nada de esto puede tumbar una ejecución: recoger la traza es observabilidad, y
observar no puede romper lo observado.
"""
from __future__ import annotations

import hashlib
import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

#: Cuánto texto de entrada/salida se guarda. La traza explica una ejecución, no
#: es un segundo almacén del artículo: el cuerpo completo ya está en `articles`.
MAX_TEXTO = 4000


@dataclass
class StepAccumulator:
    """Lo que se va anotando mientras corre un paso."""

    tokens_in: int = 0
    tokens_out: int = 0
    rag_sources: List[Dict[str, Any]] = field(default_factory=list)


_paso: ContextVar[Optional[StepAccumulator]] = ContextVar("explain_step", default=None)


def current() -> Optional[StepAccumulator]:
    return _paso.get()


@contextmanager
def collecting():
    """Abre un acumulador para el paso en curso y lo devuelve al cerrarlo.

    Es un `ContextVar`, así que cada ejecución concurrente tiene el suyo: dos
    pipelines a la vez no se mezclan las fuentes ni los tokens.
    """
    acumulador = StepAccumulator()
    token = _paso.set(acumulador)
    try:
        yield acumulador
    finally:
        _paso.reset(token)


def record_tokens(entrada: Optional[int], salida: Optional[int]) -> None:
    """Suma los tokens de una llamada al LLM al paso en curso.

    Se **suma** y no se asigna porque un paso puede llamar al LLM varias veces
    (el redactor amplía el borrador si se queda corto), y el coste del paso es el
    total.
    """
    acumulador = _paso.get()
    if acumulador is None:
        return
    try:
        acumulador.tokens_in += int(entrada or 0)
        acumulador.tokens_out += int(salida or 0)
    except Exception:  # pragma: no cover - defensivo
        logger.debug("No se pudieron anotar los tokens del paso", exc_info=True)


def record_rag_hits(collection: str, resultados: Iterable[Dict[str, Any]]) -> None:
    """Anota lo que una búsqueda RAG devolvió de verdad.

    Se agrupa por documento y se acumulan sus `chunk_ids`: la pregunta que
    responde la traza es «¿de qué documentos salió esto?», y una lista de
    fragmentos sueltos obliga a reconstruirlo a mano.
    """
    acumulador = _paso.get()
    if acumulador is None:
        return
    try:
        por_doc: Dict[str, Dict[str, Any]] = {
            fuente["doc_id"]: fuente for fuente in acumulador.rag_sources
        }
        for item in resultados or []:
            doc_id = str(item.get("doc_id") or "")
            if not doc_id:
                continue
            fuente = por_doc.get(doc_id)
            if fuente is None:
                fuente = {
                    "doc_id": doc_id,
                    "collection": collection,
                    "title": (item.get("doc_title") or item.get("filename") or "").strip(),
                    "authors": (item.get("doc_authors") or "").strip(),
                    "chunk_ids": [],
                    "score": None,
                }
                por_doc[doc_id] = fuente
                acumulador.rag_sources.append(fuente)

            chunk_id = item.get("chunk_id")
            if chunk_id is not None and chunk_id not in fuente["chunk_ids"]:
                fuente["chunk_ids"].append(chunk_id)

            score = item.get("score")
            if score is not None:
                # El mejor fragmento representa al documento: es el que decidió
                # que ese documento entrara en el contexto.
                anterior = fuente["score"]
                fuente["score"] = score if anterior is None else max(anterior, score)
    except Exception:  # pragma: no cover - defensivo
        logger.debug("No se pudieron anotar las fuentes RAG del paso", exc_info=True)


# ── Construcción del registro ───────────────────────────────────────────────

def _recortar(texto: Any) -> Optional[str]:
    if texto is None:
        return None
    texto = str(texto)
    if len(texto) <= MAX_TEXTO:
        return texto
    return texto[:MAX_TEXTO] + f"\n…[recortado, {len(texto)} caracteres en total]"


def input_digest(state: Dict[str, Any]) -> str:
    """Resumen legible de con qué entró el agente al paso.

    No es el prompt: el prompt lo compone cada agente y llevarlo entero
    duplicaría el borrador y las fuentes en cada fila. Esto es lo que permite
    entender la entrada sin reconstruirla.
    """
    partes = [
        f"título: {state.get('title') or '—'}",
        f"palabras clave: {', '.join(state.get('keywords') or []) or '—'}",
        f"investigación: {len((state.get('research_data') or '').split())} palabras",
        f"borrador: {len((state.get('draft_text') or '').split())} palabras",
        f"vuelta del bucle: {state.get('loop_count', 0)}",
    ]
    feedback = state.get("feedback") or []
    if feedback:
        partes.append(f"feedback recibido: {len(feedback)} comentario(s)")
    return " · ".join(partes)


def output_text(salida: Dict[str, Any]) -> Optional[str]:
    """El texto que el paso produjo, sea cual sea el campo en que lo deje."""
    for clave in ("formatted_text", "draft_text", "research_data", "published_url"):
        valor = salida.get(clave)
        if valor:
            return _recortar(valor)
    return None


def decision_of(salida: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Decisión del paso, si la hay: score, coherencia y desenlace del HITL.

    Solo la tienen los pasos que **deciden** —hoy el revisor—; para el resto la
    columna queda a `NULL`, que dice más que un diccionario vacío.
    """
    claves = ("approval_score", "coherent", "user_decision", "review_status")
    if not any(clave in salida for clave in claves):
        return None
    status = salida.get("review_status")
    # Una revisión no verificada no tiene puntuación: no se traza el 0 del enrutador.
    score = None if status == "not_verified" else salida.get("approval_score")
    decision = {
        "score": score,
        "coherent": salida.get("coherent"),
        "hitl_outcome": salida.get("user_decision"),
    }
    if status is not None:
        decision["review_status"] = status
    return decision


def rationale_of(salida: Dict[str, Any]) -> Optional[str]:
    """El porqué de la decisión, en palabras: el feedback del revisor."""
    feedback = salida.get("feedback")
    if not feedback:
        return None
    if isinstance(feedback, str):
        return _recortar(feedback)
    return _recortar("\n".join(f"- {item}" for item in feedback))


def params_of(agent_name: str, state: Dict[str, Any]) -> Dict[str, Any]:
    """Parámetros con los que corrió el agente, de sus ajustes de ejecución."""
    ajustes = (state.get("agent_settings") or {}).get(agent_name) or {}
    interesantes = (
        "temperature", "num_ctx", "target_word_count", "output_language",
        "scientific_format", "rag_collection", "rag_top_k", "graph_rag_enabled",
        "semantic_search_enabled",
    )
    return {clave: ajustes[clave] for clave in interesantes if clave in ajustes}


# ── Lectura de la traza (SPEC-014 / T9.2 / AC2) ─────────────────────────────
#
# La otra mitad del módulo. Escribir la traza es anotar lo que solo sabe quien lo
# produce; leerla es contestar «por qué salió esto», y esa pregunta no se responde
# con la tabla en crudo: hay que separar ejecuciones y agregar fuentes.
#
# Funciones puras sobre una lista de pasos, a propósito: es la lógica que más
# fácil se equivoca y así se prueba sin base de datos ni pipeline.

def group_executions(pasos: List[Any]) -> List[List[Any]]:
    """Parte los pasos —en orden cronológico— en ejecuciones del pipeline.

    Un artículo se puede reejecutar, y entonces su traza tiene los pasos de
    varias ejecuciones **en la misma tabla**. Ordenarlos por `step_index` los
    entrelazaría: dos ejecuciones tienen las dos un paso 0, un paso 1… y el panel
    contaría una historia que no ocurrió.

    Lo que las separa es que `step_index` **vuelve a 0**: el orquestador lo
    reinicia en cada ejecución nueva. Una reanudación (`resume`) no reinicia
    —continúa desde el checkpoint—, así que sigue la numeración y aparece como lo
    que es: la misma ejecución, terminada en un segundo intento.

    No se agrupa por `run_id` porque no es lo que se cree: `log_run_start` mina
    uno **por paso**, no por ejecución. Ni por `correlation_id`, que puede faltar.
    """
    ejecuciones: List[List[Any]] = []
    for paso in pasos:
        if not ejecuciones or (paso.step_index == 0 and ejecuciones[-1]):
            ejecuciones.append([])
        ejecuciones[-1].append(paso)
    return ejecuciones


# ── Cadena de integridad (SPEC-029 / T17.2 / AC4) ───────────────────────────

#: Versión de la serialización canónica. Va **en la fila**, no solo aquí: si
#: mañana cambia qué campos entran o cómo se formatean, las cadenas ya escritas
#: tienen que seguir verificándose con la versión que las produjo. Sin este
#: número, un cambio de formato convertiría toda la traza vieja en «manipulada».
CANON_VERSION: int = 1

#: Ancla del primer paso de cada ejecución (AC4: «ancla en un valor conocido»).
#: Es un valor fijo y público: no aporta secreto, aporta que la cadena empiece en
#: algo definido en vez de en nada, para que insertar un paso al principio rompa
#: el enlace igual que insertarlo en medio.
ANCLA_GENESIS: str = "0" * 64

#: Qué entra en el hash, en este orden. Explícito y no «todo lo que haya», para
#: que añadir una columna a la tabla no invalide en silencio las cadenas previas:
#: ampliar esta lista obliga a subir CANON_VERSION.
_CAMPOS_CANONICOS = (
    "article_id", "project_id", "agent_name", "step_index", "iteration",
    "status", "error_message", "model", "params", "input_digest",
    "output_text", "rag_sources", "tokens_in", "tokens_out", "latency_ms",
    "decision", "rationale",
)

#: Fuera del hash, a propósito:
#:   * `id` y `run_id` son claves sustitutas, no contenido.
#:   * `correlation_id` sirve para cruzar logs y puede faltar.
#:   * `created_at` no entra porque no sobrevive de forma fiable al viaje de ida
#:     y vuelta por SQLite —precisión y zona horaria varían— y una cadena que da
#:     falsos positivos por eso entrena a ignorar la alarma. La **posición** de
#:     cada paso sí queda protegida, pero por el encadenado (`prev_hash`), que es
#:     el mecanismo que AC5 necesita para detectar borrados e inserciones.
#: Esto es parte de lo que la pestaña de integridad debe declarar (AC6).


def _normalizar(clave: str, valor: Any) -> Any:
    """Lleva un valor a una forma estable entre escritura y verificación.

    Los UUID se comparan como texto porque el driver puede devolverlos como
    objeto o como cadena según de dónde venga la fila. Los flotantes se redondean
    a una décima: el único que entra es `latency_ms`, y su dígito dieciséis no
    dice nada que merezca un falso positivo.
    """
    if valor is None:
        return None
    if clave in ("article_id", "project_id"):
        return str(valor)
    if isinstance(valor, float):
        return round(valor, 1)
    return valor


def canonical_form(paso: Any, *, version: int = CANON_VERSION) -> str:
    """Serialización canónica de un paso: orden de claves y formato fijos.

    Acepta tanto el `dict` de campos con el que se escribe la fila como la fila
    ya leída de la base, para que escribir y verificar usen exactamente el mismo
    código. Dos implementaciones que «deberían coincidir» acaban no coincidiendo.
    """
    def leer(clave: str) -> Any:
        bruto = paso.get(clave) if isinstance(paso, dict) else getattr(paso, clave, None)
        return _normalizar(clave, bruto)

    datos = {clave: leer(clave) for clave in _CAMPOS_CANONICOS}
    datos["__v"] = version
    # `sort_keys` para que el orden no dependa del dict, y separadores sin
    # espacios para que no dependa del formateador.
    return json.dumps(datos, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


def compute_hash(paso: Any, prev_hash: Optional[str], *,
                 version: int = CANON_VERSION) -> str:
    """`sha256(canónico(paso) || hash_anterior)` (AC4).

    El hash anterior entra **dentro** del digest, no al lado: así cada eslabón
    depende de todos los anteriores y no se puede recolocar un paso sin que el
    resto deje de cuadrar.
    """
    material = f"{canonical_form(paso, version=version)}|{prev_hash or ANCLA_GENESIS}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def verify_chain(pasos: List[Any]) -> Dict[str, Any]:
    """Verifica la cadena de **una** ejecución (AC5).

    Recibe los pasos de una sola ejecución, en orden cronológico — tal y como los
    deja `group_executions`. Agrupar por otro criterio haría que dos ejecuciones
    del mismo artículo parecieran una cadena rota (AC7).

    Devuelve qué se comprobó y, si algo no cuadra, **cuál** paso y en qué
    posición. Un informe que solo dijera «la cadena está rota» obligaría a
    revisar la ejecución entera a mano.
    """
    problemas: List[Dict[str, Any]] = []
    sin_cadena = 0
    anterior: Optional[str] = None

    for posicion, paso in enumerate(pasos):
        guardado = getattr(paso, "content_hash", None)
        version = getattr(paso, "hash_version", None) or CANON_VERSION

        if not guardado:
            # Paso anterior a T17.2, o escrito cuando el hashing falló. No es
            # manipulación: es ausencia de prueba, y decir lo contrario sería
            # exactamente la confianza infundada que AC6 quiere evitar.
            sin_cadena += 1
            anterior = None
            continue

        esperado_prev = getattr(paso, "prev_hash", None)
        if anterior is not None and esperado_prev != anterior:
            problemas.append({
                "position": posicion,
                "step_index": getattr(paso, "step_index", None),
                "agent_name": getattr(paso, "agent_name", None),
                "problem": "enlace_roto",
                "detail": (
                    "El paso no enlaza con el anterior: falta un paso por medio, "
                    "se insertó uno, o se reordenaron."
                ),
            })

        recalculado = compute_hash(paso, esperado_prev, version=version)
        if recalculado != guardado:
            problemas.append({
                "position": posicion,
                "step_index": getattr(paso, "step_index", None),
                "agent_name": getattr(paso, "agent_name", None),
                "problem": "contenido_alterado",
                "detail": "El contenido del paso no produce el hash que tiene guardado.",
            })

        anterior = guardado

    verificados = len(pasos) - sin_cadena

    # Tres estados, no dos. Una ejecución anterior a T17.2 no tiene ni un hash:
    # no hay nada roto, no hay nada que comprobar. Colapsarlo en `intact: False`
    # la pintaba como cadena rota, que es el alarmismo que esta función existe
    # para evitar —y entrena a ignorar la alarma cuando sí sea de verdad—.
    if problemas:
        estado = "rota"
    elif verificados == 0:
        estado = "sin_cadena"
    else:
        estado = "intacta"

    return {
        "steps": len(pasos),
        "verified": verificados,
        "unchained": sin_cadena,
        "status": estado,
        "intact": estado == "intacta",
        "issues": problemas,
        "canon_version": CANON_VERSION,
    }


def aggregate_sources(pasos: Iterable[Any]) -> List[Dict[str, Any]]:
    """Fuentes RAG de todos los pasos, agrupadas por documento.

    Mismo criterio que al recogerlas dentro de un paso: se conserva el **mejor**
    score y se unen los fragmentos, porque la pregunta es «¿de qué documentos
    salió esto?». Se añade `used_by`: qué agentes lo recuperaron, que es lo que
    distingue una fuente que solo vio el investigador de una que además usó el
    redactor al ampliar el borrador.
    """
    agregadas: Dict[str, Dict[str, Any]] = {}
    for paso in pasos:
        for fuente in (paso.rag_sources or []):
            if not isinstance(fuente, dict):
                continue
            doc_id = str(fuente.get("doc_id") or "")
            if not doc_id:
                continue
            actual = agregadas.setdefault(doc_id, {
                "doc_id": doc_id, "title": None, "authors": None,
                "collection": None, "score": 0.0, "chunk_ids": [], "used_by": [],
            })
            for clave in ("title", "authors", "collection"):
                if actual[clave] is None and fuente.get(clave):
                    actual[clave] = fuente[clave]
            try:
                puntuacion = float(fuente.get("score") or 0.0)
            except (TypeError, ValueError):
                puntuacion = 0.0
            actual["score"] = max(actual["score"], puntuacion)
            for chunk in (fuente.get("chunk_ids") or []):
                if chunk not in actual["chunk_ids"]:
                    actual["chunk_ids"].append(chunk)
            if paso.agent_name not in actual["used_by"]:
                actual["used_by"].append(paso.agent_name)

    # De mejor a peor score: la fuente que más pesó, primero.
    return sorted(agregadas.values(), key=lambda f: f["score"], reverse=True)


def totals_of(pasos: List[Any]) -> Dict[str, Any]:
    """Lo que costó lo que se está leyendo."""
    agentes: List[str] = []
    for paso in pasos:
        if paso.agent_name not in agentes:
            agentes.append(paso.agent_name)
    return {
        "steps": len(pasos),
        "agents": agentes,
        "tokens_in": sum(paso.tokens_in or 0 for paso in pasos),
        "tokens_out": sum(paso.tokens_out or 0 for paso in pasos),
        "latency_ms": round(sum(paso.latency_ms or 0.0 for paso in pasos), 2),
        "loops": max((paso.iteration or 0 for paso in pasos), default=0),
        "failed_steps": sum(1 for paso in pasos if paso.status != "completed"),
    }
