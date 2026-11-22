"""Metadatos del manuscrito que pone el sistema, no el modelo (SPEC-037 / T25.1).

Autor, filiación y fecha son hechos del registro (``ArticleModel.authors`` y
``created_at``). Un LLM que los escribe los inventa —«Autor: [Su Nombre/Autoría]»,
«Fecha: Octubre 2023 (Borrador)»—, así que al componer el manuscrito se **descartan**
las líneas de esos campos del encabezado del texto y la maquetación los inyecta
desde la base.

Solo se toca el *encabezado* (antes del primer ``##``, máx. ``_MAX_FRONT_LINES``
líneas): el cuerpo científico queda intacto, de modo que una frase con «Fecha:» en
mitad de un párrafo no se altera.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List, Tuple

_MAX_FRONT_LINES = 30

_FIELDS = (
    r"autor(?:es|a|as)?|author(?:s)?|afiliaci[oó]n(?:es)?|affiliation(?:s)?|"
    r"instituci[oó]n|institution|fecha|date|correo|e-?mail"
)
# Línea «Campo: valor» con decoración Markdown opcional (>, -, *, **, _, #).
_META_LINE = re.compile(
    rf"^[\s>\-*_#]*(?:{_FIELDS})[\s*_]*[:：]", re.IGNORECASE
)
_H2 = re.compile(r"^\s{0,3}#{2,6}\s")


def strip_llm_metadata(text: str) -> Tuple[str, List[str]]:
    """Quita del encabezado las líneas de autor/filiación/fecha escritas por el LLM.

    Devuelve ``(texto_limpio, líneas_descartadas)``.
    """
    if not text:
        return text or "", []
    lines = text.split("\n")
    removed: List[str] = []
    kept: List[str] = []
    in_front = True
    for i, line in enumerate(lines):
        if in_front and (i >= _MAX_FRONT_LINES or _H2.match(line)):
            in_front = False
        if in_front and _META_LINE.match(line):
            removed.append(line.strip())
            continue
        kept.append(line)
    return "\n".join(kept), removed


def system_authors(authors: Any) -> List[Dict[str, Any]]:
    """Autores registrados con nombre; nunca inventa uno si no hay."""
    out: List[Dict[str, Any]] = []
    for a in authors or []:
        if isinstance(a, dict) and (a.get("name") or "").strip():
            out.append(a)
    return out


def system_date(created_at: Any) -> str:
    """Fecha de creación del artículo en ISO (YYYY-MM-DD); vacío si no se conoce."""
    if isinstance(created_at, (datetime, date)):
        return created_at.strftime("%Y-%m-%d")
    return ""
