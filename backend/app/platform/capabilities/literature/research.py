"""Bloque `research:` de `template.yaml` (SPEC-034 / AC1).

Se valida **al cargar la plantilla**: una base desconocida es un `ResearchConfigError`
(que el loader convierte en `TemplateError`), no un fallo a mitad de la ejecución.

Claves: `sources` (T22.1) y `min_sources` (T22.5, AC7): el número mínimo de fuentes
**verificadas** por encima del umbral de similitud con el que el Investigador investiga; con
menos, se abstiene. Es un dato **de la plantilla del proyecto**: el autor no lo puede bajar
desde el artículo ni desde los ajustes de ejecución (el Investigador solo lo lee de aquí). Una
clave desconocida se rechaza, para que un error de escritura no se quede en silencio.

Semantic Scholar es válida en `sources` aunque no haya clave: la plantilla es un dato del
proyecto y no puede cambiar de validez según el entorno donde se cargue. Sin clave, la
base se omite en tiempo de ejecución con un aviso explícito (ver `discovery.py`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple

from app.platform.capabilities.literature.models import DEFAULT_SOURCES, KNOWN_SOURCES

CLAVES_SOPORTADAS = ("sources", "min_sources")

#: N de la abstención (SPEC-034 Clarifications): por defecto 3, entero >= 1.
DEFAULT_MIN_SOURCES = 3


class ResearchConfigError(ValueError):
    """El bloque `research:` no es utilizable. El mensaje dice por qué."""


@dataclass(frozen=True)
class ResearchConfig:
    sources: Tuple[str, ...] = DEFAULT_SOURCES
    min_sources: int = DEFAULT_MIN_SOURCES


def _parse_min_sources(crudo: Any) -> int:
    if crudo is None:
        return DEFAULT_MIN_SOURCES
    # `bool` es un `int` en Python: `true` no es un número de fuentes.
    if isinstance(crudo, bool) or not isinstance(crudo, int) or crudo < 1:
        raise ResearchConfigError(
            f"'research.min_sources' debe ser un entero >= 1, no {crudo!r}"
        )
    return crudo


def parse_research(crudo: Any) -> ResearchConfig:
    """Valida el bloque `research:`. `None` o ausente -> valores por defecto."""
    if crudo is None:
        return ResearchConfig()
    if not isinstance(crudo, dict):
        raise ResearchConfigError("'research' debe ser un mapa")
    desconocidas = sorted(set(crudo) - set(CLAVES_SOPORTADAS))
    if desconocidas:
        raise ResearchConfigError(
            f"'research' tiene claves que no se reconocen: {', '.join(map(str, desconocidas))} "
            f"(se admiten: {', '.join(CLAVES_SOPORTADAS)})"
        )
    minimo = _parse_min_sources(crudo.get("min_sources"))
    if "sources" not in crudo or crudo["sources"] is None:
        return ResearchConfig(min_sources=minimo)
    fuentes = crudo["sources"]
    if not isinstance(fuentes, list) or not fuentes:
        raise ResearchConfigError("'research.sources' debe ser una lista no vacía")
    nombres = []
    for fuente in fuentes:
        if not isinstance(fuente, str):
            raise ResearchConfigError(f"'research.sources' solo admite nombres de base, no {fuente!r}")
        nombre = fuente.strip().lower()
        if nombre not in KNOWN_SOURCES:
            raise ResearchConfigError(
                f"'research.sources' nombra la base desconocida {fuente!r} "
                f"(conocidas: {', '.join(KNOWN_SOURCES)})"
            )
        if nombre in nombres:
            raise ResearchConfigError(f"'research.sources' repite la base '{nombre}'")
        nombres.append(nombre)
    return ResearchConfig(sources=tuple(nombres), min_sources=minimo)

