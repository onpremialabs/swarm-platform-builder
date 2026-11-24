"""Detección determinista de secciones de un documento académico (SPEC-034 AC15 / T22.14).

Por qué existe: ``rag.chunk_text`` trocea por párrafos sin saber en qué parte del
artículo está, y las listas bibliográficas puntúan alto frente a consultas por
tema, así que acababan recuperándose como «evidencia». Aquí se clasifica el texto
por sección **antes** de trocearlo, de modo que cada fragmento lleve ``section``
y los de ``references`` puedan quedar fuera de la búsqueda semántica (conservando
su texto en el documento para extraer metadatos, AC4).

Principios:

* **Determinista, sin LLM**: encabezados por coincidencia exacta de línea.
* **Conservador**: ante duda, ``other``. La única sección que se excluye de la
  recuperación es ``references``, y solo se declara cuando hay un encabezado
  inequívoco **y** el contenido que sigue parece de verdad una bibliografía
  (densidad de años/DOI). Un encabezado «References» sobre prosa se queda en
  ``other``.
* Un texto sin encabezados reconocibles es un único tramo ``other``: el
  comportamiento es idéntico al troceado de siempre.
"""
from __future__ import annotations

import re
from typing import List, Tuple

REFERENCES = "references"
OTHER = "other"
SECTIONS = ("abstract", "introduction", "methods", "results", "discussion",
            "conclusion", REFERENCES, OTHER)

# Encabezados (en minúsculas, sin numeración ni puntuación final) -> sección.
_HEADINGS = {
    "abstract": "abstract", "resumen": "abstract",
    "introduction": "introduction", "introducción": "introduction", "introduccion": "introduction",
    "methods": "methods", "method": "methods", "methodology": "methods",
    "materials and methods": "methods", "methods and materials": "methods",
    "online methods": "methods",
    "método": "methods", "métodos": "methods", "metodo": "methods", "metodos": "methods",
    "metodología": "methods", "metodologia": "methods", "materiales y métodos": "methods",
    "results": "results", "resultados": "results", "results and discussion": "results",
    "resultados y discusión": "results",
    "discussion": "discussion", "discusión": "discussion", "discusion": "discussion",
    "conclusion": "conclusion", "conclusions": "conclusion", "conclusión": "conclusion",
    "conclusiones": "conclusion", "concluding remarks": "conclusion",
    "references": REFERENCES, "reference": REFERENCES, "bibliography": REFERENCES,
    "literature cited": REFERENCES, "works cited": REFERENCES,
    "referencias": REFERENCES, "bibliografía": REFERENCES, "bibliografia": REFERENCES,
    "referencias bibliográficas": REFERENCES, "referencias bibliograficas": REFERENCES,
}

# Encabezados que cierran un tramo (bibliografía incluida) y no son contenido
# sustantivo: el texto que sigue es ``other``, no referencias.
_STOP_HEADINGS = {
    "acknowledgements", "acknowledgments", "acknowledgement", "acknowledgment",
    "agradecimientos", "appendix", "appendices", "apéndice", "apendice", "anexo", "anexos",
    "supplementary information", "supplementary material", "supplementary materials",
    "author contributions", "author contributions statement", "competing interests",
    "conflict of interest", "conflicts of interest", "declaration of competing interest",
    "funding", "data availability", "code availability", "data availability statement",
    "ethics statement", "financiación", "financiacion", "financiamiento",
    "conflicto de intereses", "contribuciones de los autores",
}

_NUM_PREFIX = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?|[IVX]{1,5}\.)\s+")
_ABSTRACT_INLINE = re.compile(r"^\s*(abstract|resumen)\s*[.:—–-]\s*\S", re.IGNORECASE)
_YEAR_OR_DOI = re.compile(r"\b(?:1[89]\d\d|20[0-4]\d)\b|10\.\d{4,9}/")

_MIN_HITS = 5
_MIN_DENSITY = 2.5  # años/DOI por cada 1000 caracteres


def _clasificar_linea(linea: str) -> str | None:
    """Sección que abre esta línea si es un encabezado; ``"stop"`` si cierra; si no, None."""
    s = linea.strip()
    if not s or len(s) > 60:
        return None
    if _ABSTRACT_INLINE.match(s):
        return "abstract"
    s = _NUM_PREFIX.sub("", s).strip().rstrip(":.").strip().lower()
    if s in _HEADINGS:
        return _HEADINGS[s]
    if s in _STOP_HEADINGS:
        return "stop"
    return None


def parece_bibliografia(texto: str) -> bool:
    """¿Este tramo se parece a una lista de referencias? (densidad de años/DOI)."""
    if len(texto) < 200:
        return False
    hits = len(_YEAR_OR_DOI.findall(texto))
    return hits >= _MIN_HITS and hits * 1000.0 / len(texto) >= _MIN_DENSITY


def split_sections(text: str) -> List[Tuple[str, str]]:
    """Parte ``text`` en tramos ``(section, texto)`` contiguos, en orden y sin pérdida.

    La concatenación de los tramos (con sus saltos de línea) reconstruye el texto
    original: nada se descarta aquí.
    """
    lineas = text.split("\n")
    marcas: List[Tuple[int, str]] = []  # (índice de línea, sección que abre)
    for i, linea in enumerate(lineas):
        sec = _clasificar_linea(linea)
        if sec is not None:
            marcas.append((i, sec))

    if not marcas:
        return [(OTHER, text)] if text.strip() else []

    tramos: List[Tuple[str, str]] = []
    inicio_otro = marcas[0][0]
    if inicio_otro > 0:
        previo = "\n".join(lineas[:inicio_otro])
        if previo.strip():
            tramos.append((OTHER, previo))

    for n, (idx, sec) in enumerate(marcas):
        fin = marcas[n + 1][0] if n + 1 < len(marcas) else len(lineas)
        cuerpo = "\n".join(lineas[idx:fin])
        if not cuerpo.strip():
            continue
        if sec == "stop":
            etiqueta = OTHER
        elif sec == REFERENCES:
            # Conservador: sin aspecto de bibliografía, no se excluye nada.
            etiqueta = REFERENCES if parece_bibliografia(cuerpo) else OTHER
        else:
            etiqueta = sec
        tramos.append((etiqueta, cuerpo))
    return tramos
