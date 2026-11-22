"""Búsqueda de literatura de principio a fin, con su registro (SPEC-034 / T22.7 / AC6).

`run_literature_search` es **el** punto que ejecuta descubrimiento (T22.1) +
verificación (T22.2) + registro (T22.3): lo que llame a las bases sin pasar por aquí
no deja rastro, y una búsqueda que no se puede reproducir no sirve para declarar el
método del artículo. Por eso el registro se escribe también cuando la búsqueda sale
**parcial** (alguna base falló, se limitó o se omitió) o **fallida** (ninguna respondió,
o algo reventó a medias): son justo las que hay que poder explicar.

Qué se guarda y qué no:

* Se guarda la **cadena de búsqueda** (la que ya validó `clean_query`: corta, no un
  fragmento del manuscrito), las bases, los filtros, la fecha (UTC; es la fecha de
  corte de AC2) y recuentos: devueltos, verificados y descartados por motivo.
* **No** se guardan los mensajes de error de las bases (`BaseReport.message`): pueden
  llevar la URL consultada, y con ella la clave de API o el correo de contacto
  configurado. Se guarda solo `error_kind`, una etiqueta cerrada.
* Tampoco el texto del manuscrito, cabeceras ni el `user_id` en la exportación.

Además de escribir en `search_logs`, anota la búsqueda en el paso en curso de la traza
(`explainability.record_search`), de modo que el Investigador queda trazado sin que
nadie lo instrumente (T9.1).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, Mapping, Optional
from uuid import UUID

from app.platform import explainability, library
from app.platform.capabilities.literature.discovery import (
    clean_query, search_literature, validate_sources,
)
from app.platform.capabilities.literature.models import DEFAULT_SOURCES, LiteratureResult
from app.platform.capabilities.literature.transport import LiteratureConfig
from app.platform.capabilities.literature.verification import (
    VerificationResult, library_dois_of, verify_candidates,
)

logger = logging.getLogger(__name__)

#: Cuánto de un filtro se guarda: son parámetros de búsqueda (años, tipo, idioma), no texto.
_MAX_FILTROS = 20
_MAX_VALOR = 200


@dataclass(frozen=True)
class LiteratureSearchOutcome:
    """Lo que devuelve la búsqueda: los resultados y el registro que la describe."""

    literature: LiteratureResult
    verification: VerificationResult
    log: Any  # SearchLogModel

    @property
    def status(self) -> str:
        return self.log.status


def sanitize_filters(filters: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Filtros apto para persistir: claves de texto y valores escalares (o listas de ellos).

    Lo demás se descarta: el registro no es un cubo donde meter objetos o texto largo.
    """
    limpio: Dict[str, Any] = {}
    for clave, valor in list((filters or {}).items())[:_MAX_FILTROS]:
        if not isinstance(clave, str):
            continue
        if isinstance(valor, (list, tuple)):
            valor = [v for v in valor if isinstance(v, (str, int, float, bool))]
            valor = [v[:_MAX_VALOR] if isinstance(v, str) else v for v in valor][:_MAX_FILTROS]
        elif isinstance(valor, str):
            valor = valor[:_MAX_VALOR]
        elif not isinstance(valor, (int, float, bool)) and valor is not None:
            continue
        limpio[clave[:64]] = valor
    return limpio


def _per_source(literature: LiteratureResult, verification: VerificationResult) -> Dict[str, Any]:
    """Por base: qué pasó y cuánto aportó. Sin mensajes de error (ver el docstring del módulo)."""
    cuentas = verification.per_source
    salida: Dict[str, Any] = {}
    for informe in literature.reports:
        extra = cuentas.get(informe.db, {})
        salida[informe.db] = {
            "status": informe.status,
            "returned": informe.count,
            "verified": extra.get("verified", 0),
            "dropped": informe.dropped,
            "attempts": informe.attempts,
            "error_kind": informe.error_kind or None,
        }
    return salida


async def run_literature_search(
    session: Any,
    project_id: UUID,
    query: str,
    sources: Optional[Iterable[str]] = None,
    *,
    article_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
    filters: Optional[Mapping[str, Any]] = None,
    limit: Optional[int] = None,
    config: Optional[LiteratureConfig] = None,
    fetch: Any = None,
    sleep: Any = None,
    verification: Optional[Dict[str, Any]] = None,
) -> LiteratureSearchOutcome:
    """Descubre, verifica y **registra** una búsqueda en el proyecto `project_id`.

    `query` y `sources` se validan igual que en `search_literature`: una consulta vacía,
    larga o una base desconocida levantan antes de buscar nada (no hubo búsqueda, no hay
    registro). Desde que se consulta la primera base, **siempre** se escribe un registro.

    `fetch`/`sleep` se inyectan en el descubrimiento y `verification` (`resolver`,
    `fetch`, `sleep`, `clock`, `cache`) en la verificación; son para las pruebas.
    """
    cadena = clean_query(query)
    bases = validate_sources(sources if sources is not None else DEFAULT_SOURCES)
    cfg = config or LiteratureConfig.from_settings()
    tope = max(1, limit if limit is not None else cfg.max_results)
    filtros = {**sanitize_filters(filters), "limit": tope}
    # La fecha de la búsqueda es la fecha de corte (AC2): se fija antes de consultar.
    buscada_en = datetime.utcnow()

    try:
        literatura = await search_literature(
            cadena, bases, limit=tope, config=cfg, fetch=fetch, sleep=sleep)
        if literatura.candidates:
            en_biblioteca = await library_dois_of(session, project_id, literatura.candidates)
            verificacion = await verify_candidates(
                literatura.candidates, buscada_en, library_dois=en_biblioteca,
                **(verification or {}))
        else:
            verificacion = VerificationResult(searched_at=buscada_en)
    except Exception as error:
        # Una búsqueda que revienta a medias también se registra (AC6): sin ella, quien
        # lea el método no sabría que se intentó ni con qué cadena.
        logger.exception("literature: la búsqueda falló a medias")
        log = await library.record_search(
            session, project_id, query=cadena, sources=list(bases), filters=filtros,
            per_source={db: {"status": "failed", "error_kind": "unexpected"} for db in bases},
            status="failed", article_id=article_id, user_id=user_id, searched_at=buscada_en)
        _annotate(log)
        raise

    campos = verificacion.log_fields(literatura)
    log = await library.record_search(
        session, project_id, query=cadena, sources=[r.db for r in literatura.reports],
        filters=filtros, per_source=_per_source(literatura, verificacion),
        article_id=article_id, user_id=user_id, **campos)
    _annotate(log)
    return LiteratureSearchOutcome(literatura, verificacion, log)


def _annotate(log: Any) -> None:
    """Anota la búsqueda en el paso de la traza en curso (no-op fuera de un paso)."""
    explainability.record_search({
        **library.search_record(log),
        "search_id": str(log.id),
    })
