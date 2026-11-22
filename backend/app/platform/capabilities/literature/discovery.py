"""Descubrimiento de literatura: la consulta a las bases de `research.sources`.

Es el punto de entrada de la capacidad `literature` (SPEC-034 / AC1, AC10).

Tres reglas que son el módulo:

* **Una base que falla no tumba a las demás**, pero **tampoco se oculta**: cada base
  deja un `BaseReport` (`ok` / `failed` / `skipped`) con la causa y los intentos, y el
  resultado dice si está `complete`. El llamador decide qué hacer con un resultado parcial.
* **Falla cerrada.** Un registro sin título o sin identificación se descarta (y se
  cuenta), y ningún candidato sale marcado como verificado: eso es T22.2.
* **La consulta es solo la cadena de búsqueda.** Se rechaza la vacía y la que parece un
  texto, para que ni el manuscrito ni datos de la persona usuaria salgan a terceros.

No deduplica (T22.2) ni registra la búsqueda (T22.7).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from app.platform.capabilities.literature import arxiv, crossref, openalex, pubmed, semantic_scholar
from app.platform.capabilities.literature.models import (
    ARXIV, CROSSREF, DEFAULT_SOURCES, KNOWN_SOURCES, MAX_QUERY_CHARS, OPENALEX, PUBMED,
    SEMANTIC_SCHOLAR, BaseReport, LiteratureQueryError, LiteratureResult, Parsed,
    UnknownSourceError,
)
from app.platform.capabilities.literature.transport import (
    ApiSession, Fetch, LiteratureConfig, Sleep, SourceError,
)

logger = logging.getLogger(__name__)

_CLIENTES: Dict[str, Callable[..., Any]] = {
    OPENALEX: openalex.search,
    CROSSREF: crossref.search,
    SEMANTIC_SCHOLAR: semantic_scholar.search,
    ARXIV: arxiv.search,
    PUBMED: pubmed.search,
}


def validate_sources(sources: Iterable[str]) -> Tuple[str, ...]:
    """Normaliza y valida nombres de base; una desconocida levanta `UnknownSourceError`."""
    nombres: List[str] = []
    for crudo in sources:
        nombre = str(crudo).strip().lower()
        if nombre not in KNOWN_SOURCES:
            raise UnknownSourceError(
                f"base bibliográfica desconocida: {crudo!r} (conocidas: {', '.join(KNOWN_SOURCES)})"
            )
        if nombre not in nombres:
            nombres.append(nombre)
    return tuple(nombres)


def clean_query(query: str) -> str:
    """La cadena de búsqueda, con espacios normalizados; `LiteratureQueryError` si no vale."""
    limpia = " ".join(str(query or "").split())
    if not limpia:
        raise LiteratureQueryError("la consulta está vacía")
    if len(limpia) > MAX_QUERY_CHARS:
        raise LiteratureQueryError(
            f"la consulta tiene {len(limpia)} caracteres (máximo {MAX_QUERY_CHARS}): debe ser "
            "una cadena de búsqueda, no un fragmento de texto"
        )
    return limpia


async def _consultar(db: str, query: str, cfg: LiteratureConfig, limit: int,
                     fetch: Optional[Fetch], sleep: Optional[Sleep]) -> Tuple[BaseReport, List]:
    if db == SEMANTIC_SCHOLAR and not cfg.semantic_scholar_key:
        # Decisión de diseño: la plantilla es la misma con o sin clave, así que cargar no
        # puede depender del entorno; la base se omite aquí, con motivo, y no en silencio.
        mensaje = "se omite: falta SEMANTIC_SCHOLAR_API_KEY en el entorno"
        logger.warning("literature[%s]: %s", db, mensaje)
        return BaseReport(db, "skipped", error_kind="missing_api_key", message=mensaje), []

    session = ApiSession(db, cfg, fetch=fetch, sleep=sleep)
    try:
        parsed: Parsed = await _CLIENTES[db](query, session, limit)
    except SourceError as error:
        logger.warning("literature[%s]: fallo tras %s intento(s): %s", db, error.attempts, error.detail)
        return BaseReport(db, "failed", attempts=error.attempts, error_kind=error.kind,
                          message=str(error)), []
    except Exception as error:  # un cliente roto no debe tumbar a las demás bases
        logger.exception("literature[%s]: error inesperado", db)
        return BaseReport(db, "failed", attempts=session.attempts, error_kind="invalid_response",
                          message=f"{db}: error inesperado: {type(error).__name__}: {error}"), []
    return (
        BaseReport(db, "ok", count=len(parsed.candidates), dropped=parsed.dropped,
                   attempts=session.attempts),
        parsed.candidates,
    )


async def search_literature(
    query: str,
    sources: Optional[Iterable[str]] = None,
    *,
    limit: Optional[int] = None,
    config: Optional[LiteratureConfig] = None,
    fetch: Optional[Fetch] = None,
    sleep: Optional[Sleep] = None,
) -> LiteratureResult:
    """Consulta `sources` (por defecto OpenAlex y Crossref) y devuelve candidatos **no verificados**.

    Las bases se consultan en paralelo; los candidatos salen agrupados por base en el
    orden de `sources`. Un fallo de una base no levanta: queda en `result.reports`.
    """
    cadena = clean_query(query)
    bases = validate_sources(sources if sources is not None else DEFAULT_SOURCES)
    cfg = config or LiteratureConfig.from_settings()
    tope = max(1, limit if limit is not None else cfg.max_results)

    salidas = await asyncio.gather(*(_consultar(db, cadena, cfg, tope, fetch, sleep) for db in bases))
    candidatos = [c for _, lista in salidas for c in lista]
    return LiteratureResult(query=cadena, candidates=candidatos,
                            reports=tuple(informe for informe, _ in salidas))
