"""Recorte de fragmentos citables por prioridad de sección (SPEC-036 / T24.12 / AC13).

Cuando el prompt del Redactor no cabe en la ventana del modelo no se envía recortado por el
proveedor (que descartaría texto en silencio): se quitan **fragmentos citables enteros**, y se
sabe cuáles y por qué. Funciones puras, sin red ni LLM.

Cada fragmento del Investigador declara su origen (`[Sub-pregunta q2: método]`); la sub-pregunta
lo liga a una sección (`subqueries.SECCIONES`, en orden de prioridad: problema primero). El
orden de quita, para que no se quede sin cobertura una sección si puede evitarse:

1. fragmentos **sin sección** (los del RAG propio del Redactor y los de la consulta por título);
2. el último fragmento de la sección **con más fragmentos** (empate: la de menor prioridad);
3. solo si cada sección tiene uno, el de la sección de **menor prioridad** (se pierde cobertura
   y queda registrado en `sections_lost`).

Dentro de una sección se quita el último: el Investigador los entrega ordenados por relevancia.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.platform.capabilities.subqueries import SECCIONES

_ORIGEN = re.compile(r"Sub-pregunta\s+([A-Za-z0-9_]+)\s*:")

SIN_SECCION = None


def section_of(fragmento: Dict[str, Any], subqueries: Sequence[Dict[str, Any]]) -> Optional[str]:
    """Sección que alimenta un fragmento, o `None` si no se puede saber."""
    por_id = {q.get("id"): q.get("section") for q in (subqueries or []) if isinstance(q, dict)}
    m = _ORIGEN.search(str(fragmento.get("origin") or ""))
    return por_id.get(m.group(1)) if m else None


def next_drop(secciones: Sequence[Optional[str]]) -> Optional[Tuple[int, str]]:
    """Índice del siguiente fragmento a quitar y el motivo, o `None` si no queda ninguno."""
    if not secciones:
        return None
    sin = [i for i, s in enumerate(secciones) if s not in SECCIONES]
    if sin:
        return sin[-1], "no_section"
    cuenta = {s: [i for i, x in enumerate(secciones) if x == s] for s in SECCIONES}
    # Prioridad inversa en el desempate: la última de SECCIONES se sacrifica antes.
    candidatas = [s for s in reversed(SECCIONES) if len(cuenta[s]) > 1]
    if candidatas:
        s = max(candidatas, key=lambda x: len(cuenta[x]))
        return cuenta[s][-1], "section_surplus"
    for s in reversed(SECCIONES):
        if cuenta[s]:
            return cuenta[s][-1], "section_coverage_lost"
    return None


def trim_order(fragmentos: List[Dict[str, Any]], subqueries: Sequence[Dict[str, Any]]):
    """Generador de `(fragmento, sección, motivo)` en el orden en que se irían quitando.

    Trabaja sobre una copia: quien llama decide cuántos consume (hasta que el prompt cabe).
    """
    restantes = list(fragmentos)
    secciones = [section_of(f, subqueries) for f in restantes]
    while True:
        elegido = next_drop(secciones)
        if elegido is None:
            return
        i, motivo = elegido
        yield restantes.pop(i), secciones.pop(i), motivo
