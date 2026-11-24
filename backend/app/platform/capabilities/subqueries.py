"""Sub-preguntas de sección del Investigador (SPEC-034 / T22.17 / AC18).

Recuperar solo por el título trae lo más parecido al tema, no lo que cada sección IMRaD
necesita. Aquí se piden al modelo sub-preguntas por sección (problema, método, resultados,
limitaciones) **solo a partir del título y del enfoque del autor**: nunca del manuscrito ni
del texto de las fuentes, que es contenido no confiable y no debe poder dirigir qué se busca.

Funciones puras y sin red: el prompt, el análisis de la respuesta del modelo (que se trata
como entrada no confiable) y el cálculo de cobertura se prueban sin LLM ni RAG.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional

#: Secciones que se cubren, en el orden en que se priorizan si `max_subqueries` es corto.
SECCIONES = ("problem", "method", "results", "limitations")

#: Nombre legible (es) de cada sección, para mensajes al autor y al Redactor.
ETIQUETAS = {
    "problem": "problema",
    "method": "método",
    "results": "resultados",
    "limitations": "limitaciones",
}

#: Identificador de la consulta por el título, que sigue existiendo además de las sub-preguntas.
TITULO = "title"

_MAX_PREGUNTA = 240

_PLANTILLAS = {
    "problem": "¿Qué problema o brecha de conocimiento abordan las fuentes sobre: {titulo}?",
    "method": "¿Qué método, diseño o datos emplean las fuentes sobre: {titulo}?",
    "results": "¿Qué resultados y hallazgos reportan las fuentes sobre: {titulo}?",
    "limitations": "¿Qué limitaciones y trabajo futuro señalan las fuentes sobre: {titulo}?",
}


def build_prompt(title: str, focus: str, maximo: int) -> str:
    """Prompt para proponer sub-preguntas. Solo recibe título y enfoque del autor."""
    enfoque = (focus or "").strip() or "(sin enfoque indicado)"
    return (
        "Eres un bibliotecario científico. Propón sub-preguntas de búsqueda para encontrar, en "
        "una base de artículos científicos, la evidencia que necesita cada sección de un "
        "artículo con este título y enfoque. Cada sub-pregunta debe poder responderse con el "
        "texto de un artículo (qué problema, qué método, qué resultados reportan las fuentes, "
        "qué limitaciones).\n\n"
        f"TÍTULO: {(title or '').strip()}\n"
        f"ENFOQUE DEL AUTOR: {enfoque}\n\n"
        f"Responde SOLO con un array JSON de como máximo {maximo} objetos "
        '{"section": "problem|method|results|limitations", "question": "..."}, '
        "con al menos una sub-pregunta por sección si el máximo lo permite. Sin explicaciones."
    )


def fallback_questions(title: str) -> Dict[str, str]:
    """Una sub-pregunta determinista por sección, derivada solo del título."""
    titulo = (title or "").strip() or "el tema del artículo"
    return {s: _PLANTILLAS[s].format(titulo=titulo) for s in SECCIONES}


def _items_del_modelo(crudo: Any) -> List[Dict[str, str]]:
    """Extrae `{section, question}` válidos de la respuesta del modelo; lo demás se descarta."""
    if not isinstance(crudo, str):
        return []
    coincidencia = re.search(r"\[.*\]", crudo, re.S)
    if not coincidencia:
        return []
    try:
        datos = json.loads(coincidencia.group(0))
    except (ValueError, TypeError):
        return []
    items: List[Dict[str, str]] = []
    vistos = set()
    for dato in datos if isinstance(datos, list) else []:
        if not isinstance(dato, dict):
            continue
        seccion = str(dato.get("section") or "").strip().lower()
        pregunta = re.sub(r"\s+", " ", str(dato.get("question") or "")).strip()
        if seccion not in SECCIONES or not pregunta:
            continue
        pregunta = pregunta[:_MAX_PREGUNTA]
        clave = (seccion, pregunta.lower())
        if clave in vistos:
            continue
        vistos.add(clave)
        items.append({"section": seccion, "question": pregunta})
    return items


def plan(title: str, respuesta_modelo: Optional[str], maximo: int) -> List[Dict[str, str]]:
    """Sub-preguntas finales, acotadas por `maximo` (`research.max_subqueries`).

    Primero una por sección (la del modelo, o la determinista si no propuso ninguna), para
    que un tope corto no deje secciones sin preguntar; después, las demás del modelo.
    Cada elemento: `{id, section, question}` con `id` = `q1`, `q2`, ...
    """
    propuestas = _items_del_modelo(respuesta_modelo)
    respaldo = fallback_questions(title)
    elegidas: List[Dict[str, str]] = []
    for seccion in SECCIONES:
        propia = next((p for p in propuestas if p["section"] == seccion), None)
        elegidas.append(propia or {"section": seccion, "question": respaldo[seccion]})
    restantes = [p for p in propuestas if p not in elegidas]
    elegidas = (elegidas + restantes)[: max(1, int(maximo))]
    return [{"id": f"q{i}", **e} for i, e in enumerate(elegidas, 1)]


def coverage(subqueries: List[Dict[str, str]], fragmentos: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Cobertura por sección: cuántos fragmentos **sustantivos** llegaron por sus sub-preguntas.

    `fragmentos` son los ya filtrados (citables y sustantivos); cada uno declara en
    `subqueries` los ids que lo recuperaron. Una sección sin ninguno, o sin sub-pregunta
    (el tope la dejó fuera), queda `covered=False`: es lo que se declara «sin cobertura».
    """
    por_id = {q["id"]: q["section"] for q in subqueries}
    cuenta = {s: 0 for s in SECCIONES}
    for frag in fragmentos:
        secciones = {por_id[i] for i in (frag.get("subqueries") or []) if i in por_id}
        for seccion in secciones:
            cuenta[seccion] += 1
    return [
        {"section": s, "label": ETIQUETAS[s], "covered": cuenta[s] > 0, "fragments": cuenta[s],
         "queried": any(q["section"] == s for q in subqueries)}
        for s in SECCIONES
    ]


def render_gaps(cobertura: Iterable[Dict[str, Any]], language: str = "es") -> str:
    """Aviso para el Redactor sobre las secciones sin evidencia sustantiva ('' si no hay)."""
    huecos = [c for c in (cobertura or []) if not c.get("covered")]
    if not huecos:
        return ""
    nombres = ", ".join(c.get("label") or c.get("section") or "?" for c in huecos)
    if language == "en":
        return (
            "EVIDENCE WITHOUT COVERAGE (the retrieved sources have no substantive content for: "
            f"{nombres}). Do NOT fill these with your own knowledge: in those parts say, without "
            "inventing data or citations, that the available sources do not provide evidence."
        )
    return (
        "EVIDENCIA SIN COBERTURA (las fuentes recuperadas no tienen contenido sustantivo sobre: "
        f"{nombres}). NO rellenes esas partes con tu propio conocimiento: indica en ellas, sin "
        "inventar datos ni citas, que las fuentes disponibles no aportan evidencia."
    )
