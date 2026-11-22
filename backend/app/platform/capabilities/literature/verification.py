"""Verificación de candidatos de literatura (SPEC-034 / T22.2 / AC2, AC10).

Un candidato que devuelve una base **no es una fuente**. Este módulo decide cuáles se
pueden ofrecer a la persona autora: solo los que **resuelven por DOI** contra el registro
(Crossref, OpenAlex o DataCite) y **coinciden** en título, autores y año. Es la misma
comprobación de V09 nivel 2 que hace la compuerta de publicación (SPEC-032, ADR-0011) y
**reutiliza su resolver** (`publication_gate.reference_resolver`): mismo umbral de
similitud, mismas reglas de autores y año, misma caché de positivos y mismos reintentos.
Lo único propio es la identidad de salida (`quien="literature_discovery"`) y que las
métricas de la compuerta no se tocan.

Reglas (en este orden, para gastar la red solo en lo que puede ofrecerse):

1. **Fecha futura.** Se descarta si la fecha de publicación es posterior a `searched_at`
   (la fecha de corte; queda en el resultado para el registro de búsqueda, AC6). Con una
   fecha parcial (`YYYY` o `YYYY-MM`) solo si **todo** el intervalo queda después, como en
   `publication_gate/dates.py`. Un candidato sin fecha **no** se descarta por esta regla.
2. **Duplicados** por DOI normalizado dentro del lote: se conserva el de metadatos más
   completos (a igualdad, el primero) y se anota de qué bases venían todos. Los que ya
   están en la biblioteca del proyecto no se descartan: salen marcados
   `already_in_library`.
3. **Resolución.** Con DOI, se resuelve y se compara. Sin DOI:
   * arXiv: el DOI de DataCite `10.48550/arxiv.<id>` se deriva del identificador;
   * PubMed: solo vale el DOI que informe la base (no hay conversión PMID→DOI propia);
   * el resto (y PubMed sin DOI): búsqueda por título y autores con las reglas del
     resolver; un único candidato fiable fija el DOI, y si no, se descarta.
   Sin DOI y sin título y autores con los que buscar: `no_identifier`.

**Falla cerrada** (ADR-0011): si el resolver no responde o se agotan los reintentos, el
candidato **no** se ofrece (`resolver_unavailable`, `not_verified`); nunca se verifica «por
defecto». Y nadie construye un `VerifiedCandidate` sin pasar por aquí: `verified` no es
un campo del `Candidate`.

No persiste el registro de búsqueda (T22.7), no expone API (T22.8) ni descarga PDFs (T22.10).
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from app.platform.capabilities.literature.models import (
    ARXIV, LiteratureResult, Candidate, normalize_doi,
)
from app.platform.egress import QUIEN_LITERATURA
from app.platform.publication_gate import CriterionStatus
from app.platform.publication_gate.dates import _tramo
from app.platform.publication_gate.reference_resolver import (
    NO_METRICS, Fetch, PositiveCache, ResolverConfig, fetch_for, open_session, resolve_reference,
)

logger = logging.getLogger(__name__)

#: Motivos de descarte (claves de `search_logs.discarded`).
NO_IDENTIFIER = "no_identifier"
UNRESOLVED = "unresolved"
METADATA_MISMATCH = "metadata_mismatch"
DUPLICATE = "duplicate"
FUTURE_DATE = "future_date"
RESOLVER_UNAVAILABLE = "resolver_unavailable"
DISCARD_REASONS: Tuple[str, ...] = (
    NO_IDENTIFIER, UNRESOLVED, METADATA_MISMATCH, DUPLICATE, FUTURE_DATE, RESOLVER_UNAVAILABLE,
)

#: Valor de `library_documents.verification_method` para lo que verifica esta capacidad.
VERIFICATION_METHOD = "doi_resolved"

#: De dónde salió el DOI del candidato verificado.
DOI_DECLARED = "declared"        # lo informó la base
DOI_DERIVED_ARXIV = "derived_arxiv"  # 10.48550/arxiv.<id>
DOI_BY_TITLE = "resolved_by_title"   # buscado por título y autores

_ARXIV_PREFIX = "10.48550/arxiv."
_ISO = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?")
_KIND_A_MOTIVO = {
    "not_found": UNRESOLVED,
    "mismatch": METADATA_MISMATCH,
    "unavailable": RESOLVER_UNAVAILABLE,
    "no_search_data": NO_IDENTIFIER,
    "no_match": UNRESOLVED,
    "ambiguous": UNRESOLVED,
}


@dataclass(frozen=True)
class VerifiedCandidate:
    """Candidato cuyo DOI resolvió y coincide: apto para ofrecerse a la persona autora."""

    candidate: Candidate
    doi: str
    #: Registro que lo confirmó: `crossref` | `openalex` | `datacite`.
    provider: str
    verified_at: datetime
    verification_method: str = VERIFICATION_METHOD
    doi_origin: str = DOI_DECLARED
    #: Todas las bases que lo devolvieron (incluida la de `candidate`), sin repetir.
    found_in: Tuple[str, ...] = ()
    #: Ya está en la biblioteca del proyecto: se avisa, no se descarta.
    already_in_library: bool = False
    #: Metadatos que el registro aportó y el candidato no traía.
    enriched: Tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        return {
            **self.candidate.as_dict(), "doi": self.doi, "verified": True,
            "verification_method": self.verification_method,
            "verified_at": self.verified_at.isoformat(), "provider": self.provider,
            "doi_origin": self.doi_origin, "found_in": list(self.found_in),
            "already_in_library": self.already_in_library, "enriched": list(self.enriched),
        }


@dataclass(frozen=True)
class DiscardedCandidate:
    """Candidato que **no** se ofrece, con el motivo."""

    candidate: Candidate
    reason: str
    detail: str = ""
    #: Para `duplicate`: el DOI del candidato que se conservó.
    duplicate_of: Optional[str] = None

    @property
    def not_verified(self) -> bool:
        """`True` si no se pudo comprobar (el resolver no respondió) y puede reintentarse."""
        return self.reason == RESOLVER_UNAVAILABLE

    def as_dict(self) -> Dict[str, Any]:
        return {**self.candidate.as_dict(), "reason": self.reason, "detail": self.detail,
                "duplicate_of": self.duplicate_of, "not_verified": self.not_verified}


@dataclass(frozen=True)
class VerificationResult:
    #: Fecha de corte: la de la búsqueda (AC2, AC6).
    searched_at: datetime
    verified: Tuple[VerifiedCandidate, ...] = ()
    discarded: Tuple[DiscardedCandidate, ...] = ()

    @property
    def verified_count(self) -> int:
        return len(self.verified)

    @property
    def input_count(self) -> int:
        return len(self.verified) + len(self.discarded)

    @property
    def discarded_counts(self) -> Dict[str, int]:
        """`{motivo: n}` solo con los motivos que ocurrieron; es `search_logs.discarded`."""
        contados: Dict[str, int] = {}
        for d in self.discarded:
            contados[d.reason] = contados.get(d.reason, 0) + 1
        return contados

    @property
    def unavailable_count(self) -> int:
        return sum(1 for d in self.discarded if d.not_verified)

    @property
    def per_source(self) -> Dict[str, Dict[str, int]]:
        """Por base de origen: cuántos candidatos devolvió y cuántos se ofrecen."""
        salida: Dict[str, Dict[str, int]] = {}
        for v in self.verified:
            for db in v.found_in or (v.candidate.source_db,):
                salida.setdefault(db, {"returned": 0, "verified": 0})["verified"] += 1
        for item in (*(v.candidate for v in self.verified), *(d.candidate for d in self.discarded)):
            salida.setdefault(item.source_db, {"returned": 0, "verified": 0})["returned"] += 1
        return salida

    def search_status(self, literature: Optional[LiteratureResult] = None) -> str:
        """`completed` | `partial` | `failed` (valores de `SEARCH_STATUSES`, AC10).

        `partial` si alguna base falló o se omitió, o si algún candidato no se pudo
        comprobar; `failed` si ninguna base respondió.
        """
        if literature is not None and literature.all_failed:
            return "failed"
        if (literature is not None and not literature.complete) or self.unavailable_count:
            return "partial"
        return "completed"

    def log_fields(self, literature: Optional[LiteratureResult] = None) -> Dict[str, Any]:
        """Lo que T22.7 pasa a `library.record_search`: sin rehacer cálculos."""
        return {
            "result_count": self.input_count,
            "verified_count": self.verified_count,
            "discarded": self.discarded_counts,
            "status": self.search_status(literature),
            "searched_at": self.searched_at,
        }


# ── Fechas ──────────────────────────────────────────────────────────────────

def _publication_interval(candidate: Candidate) -> Optional[Tuple[date, date]]:
    """Intervalo de días que cubre la fecha del candidato; `None` si no hay (o no es válida)."""
    texto = candidate.publication_date
    coincide = _ISO.match(texto) if texto else None
    try:
        if coincide:
            anio, mes, dia = coincide.groups()
            if mes is None:
                return date(int(anio), 1, 1), date(int(anio), 12, 31)
            return _tramo(int(anio), int(mes), int(dia) if dia else None)
        if candidate.year is not None:
            return date(candidate.year, 1, 1), date(candidate.year, 12, 31)
    except ValueError:
        return None  # 31 de febrero, mes 13: no es una fecha, no se juzga
    return None


def is_future(candidate: Candidate, searched_at: datetime) -> bool:
    """`True` solo si **todo** el intervalo de publicación es posterior al día de la búsqueda."""
    intervalo = _publication_interval(candidate)
    return intervalo is not None and intervalo[0] > searched_at.date()


# ── Duplicados ──────────────────────────────────────────────────────────────

def _completeness(c: Candidate) -> int:
    return sum(bool(v) for v in (c.authors, c.year, c.publication_date, c.journal, c.abstract,
                                 c.url, c.open_access_url))


def _arxiv_doi(c: Candidate) -> Optional[str]:
    if c.source_db == ARXIV and c.source_id:
        return f"{_ARXIV_PREFIX}{c.source_id.strip().lower()}"
    return None


def _declared_doi(c: Candidate) -> Tuple[Optional[str], str]:
    doi = normalize_doi(c.doi)
    if doi:
        return doi, DOI_DECLARED
    derivado = _arxiv_doi(c)
    return (derivado, DOI_DERIVED_ARXIV) if derivado else (None, DOI_DECLARED)


def _dedupe(candidates: Sequence[Candidate]) -> Tuple[List[Tuple[Candidate, Tuple[str, ...]]],
                                                      List[DiscardedCandidate]]:
    """Un candidato por DOI conocido (el más completo) y los descartados por duplicados."""
    grupos: Dict[str, List[Candidate]] = {}
    orden: List[Any] = []
    for c in candidates:
        doi, _ = _declared_doi(c)
        if doi is None:
            orden.append(c)
        else:
            if doi not in grupos:
                grupos[doi] = []
                orden.append(doi)
            grupos[doi].append(c)

    conservados: List[Tuple[Candidate, Tuple[str, ...]]] = []
    duplicados: List[DiscardedCandidate] = []
    for item in orden:
        if isinstance(item, Candidate):
            conservados.append((item, (item.source_db,)))
            continue
        grupo = grupos[item]
        # `max` devuelve el primero de los empatados: a igualdad manda el orden de llegada.
        mejor = max(grupo, key=_completeness)
        bases = tuple(dict.fromkeys(c.source_db for c in grupo))
        conservados.append((mejor, bases))
        duplicados += [
            DiscardedCandidate(c, DUPLICATE, f"mismo DOI que otro candidato ({item})", duplicate_of=item)
            for c in grupo if c is not mejor
        ]
    return conservados, duplicados


# ── Verificación ────────────────────────────────────────────────────────────

def _as_reference(c: Candidate, doi: Optional[str]) -> Dict[str, str]:
    """El candidato con la forma de «fuente» que entiende el resolver.

    No se pasa la revista: cada base la nombra a su manera y es la señal más débil; el
    DOI, el título, los autores y el año sí (los mismos que la compuerta comprobará
    cuando se cite).
    """
    anio = c.year
    if anio is None and c.publication_date and _ISO.match(c.publication_date):
        anio = int(c.publication_date[:4])
    return {
        "doi": doi or "", "title": c.title, "authors": ", ".join(c.authors),
        "year": str(anio) if anio is not None else "", "journal": "",
    }


async def _verify_one(sess, c: Candidate, found_in: Tuple[str, ...], now: datetime):
    doi, origen = _declared_doi(c)
    out = await resolve_reference(sess, _as_reference(c, doi))
    if out.status is CriterionStatus.PASSED:
        if doi is None:
            origen = DOI_BY_TITLE
        fuente = out.source
        faltan = tuple(
            campo for campo, valor in (("year", c.year), ("journal", c.journal), ("authors", c.authors))
            if not valor and fuente.get(campo)
        )
        return VerifiedCandidate(
            candidate=_enrich(c, fuente), doi=normalize_doi(out.doi) or "", provider=out.provider,
            verified_at=now, doi_origin=origen, found_in=found_in, enriched=faltan,
        )
    motivo = _KIND_A_MOTIVO.get(out.kind, RESOLVER_UNAVAILABLE)
    return DiscardedCandidate(c, motivo, out.reason)


def _enrich(c: Candidate, fuente: Dict[str, Any]) -> Candidate:
    """Completa lo que el candidato no traía con el registro; no pisa nada.

    El DOI también: así el candidato que sale lleva el DOI verificado. (`verified` no es un
    campo de `Candidate`, por eso `replace` es seguro.)
    """
    cambios: Dict[str, Any] = {"doi": normalize_doi(fuente.get("doi")) or c.doi}
    if c.year is None and str(fuente.get("year", "")).strip().isdigit():
        cambios["year"] = int(fuente["year"])
    if not c.journal and fuente.get("journal"):
        cambios["journal"] = str(fuente["journal"])
    if not c.authors and fuente.get("authors"):
        cambios["authors"] = tuple(a.strip() for a in str(fuente["authors"]).split(",") if a.strip())
    return replace(c, **cambios)


async def verify_candidates(
    candidates: Iterable[Candidate],
    searched_at: datetime,
    *,
    resolver: Optional[ResolverConfig] = None,
    library_dois: Optional[Iterable[str]] = None,
    fetch: Optional[Fetch] = None,
    cache: Optional[PositiveCache] = None,
    sleep: Optional[Callable[[float], Any]] = None,
    clock: Optional[Callable[[], float]] = None,
    concurrency: int = 4,
) -> VerificationResult:
    """Verifica `candidates` y devuelve los aptos para ofrecer y los descartados con motivo.

    `searched_at` es la fecha de corte y se devuelve tal cual en el resultado.
    `resolver` es el `gate.references` del proyecto (umbral de similitud, reintentos…);
    sin él, los valores por defecto de la compuerta. `library_dois` son los DOI que el
    proyecto ya tiene en su biblioteca (véase `library_dois_of`), para marcar
    `already_in_library`. `fetch`, `sleep`, `clock` y `cache` se inyectan en las pruebas.
    """
    lote = list(candidates)
    ahora = datetime.utcnow()
    descartados: List[DiscardedCandidate] = []

    # 1. Fecha futura: no hace falta preguntarle nada a la red.
    vigentes: List[Candidate] = []
    for c in lote:
        if is_future(c, searched_at):
            descartados.append(DiscardedCandidate(
                c, FUTURE_DATE,
                f"publicación {c.publication_date or c.year} posterior a la búsqueda "
                f"({searched_at.date().isoformat()})"))
        else:
            vigentes.append(c)

    # 2. Duplicados por DOI conocido (antes de gastar peticiones).
    unicos, duplicados = _dedupe(vigentes)
    descartados += duplicados

    # 3. Resolución, con concurrencia acotada y la identidad de la capacidad.
    cfg = resolver or ResolverConfig()
    if not cfg.contact_email:
        from app.core.config import settings

        cfg = replace(cfg, contact_email=(settings.LITERATURE_CONTACT_EMAIL or "").strip())
    kwargs: Dict[str, Any] = {}
    if sleep is not None:
        kwargs["sleep"] = sleep
    if clock is not None:
        kwargs["clock"] = clock
    sess = open_session(
        cfg, fetch=fetch or fetch_for(QUIEN_LITERATURA), cache=cache, metrics=NO_METRICS,
        user_agent="AlejandrIA-LiteratureDiscovery/1.0", **kwargs,
    )
    limite = asyncio.Semaphore(max(1, concurrency))

    async def uno(c: Candidate, bases: Tuple[str, ...]):
        async with limite:
            try:
                return await _verify_one(sess, c, bases, ahora)
            except Exception as error:  # falla cerrada: un fallo inesperado nunca verifica
                logger.exception("literature: error inesperado verificando %r", c.title)
                return DiscardedCandidate(c, RESOLVER_UNAVAILABLE,
                                          f"error inesperado: {type(error).__name__}: {error}")

    resultados = await asyncio.gather(*(uno(c, b) for c, b in unicos))

    # 4. Duplicados que solo se ven tras resolver (DOI hallado por título o por el registro).
    biblioteca: Set[str] = {d for d in (normalize_doi(x) for x in library_dois or ()) if d}
    verificados: List[VerifiedCandidate] = []
    vistos: Dict[str, VerifiedCandidate] = {}
    for r in resultados:
        if isinstance(r, DiscardedCandidate):
            descartados.append(r)
            continue
        previo = vistos.get(r.doi)
        if previo is None:
            vistos[r.doi] = r
            verificados.append(r)
            continue
        ganador, perdedor = (r, previo) if _completeness(r.candidate) > _completeness(previo.candidate) \
            else (previo, r)
        bases = tuple(dict.fromkeys((*ganador.found_in, *perdedor.found_in)))
        nuevo = replace(ganador, found_in=bases)
        vistos[r.doi] = nuevo
        verificados[verificados.index(previo)] = nuevo
        descartados.append(DiscardedCandidate(
            perdedor.candidate, DUPLICATE, f"mismo DOI que otro candidato ({r.doi})",
            duplicate_of=r.doi))

    # 5. Ya en la biblioteca: se avisa, no se descarta.
    verificados = [replace(v, already_in_library=v.doi in biblioteca) for v in verificados]
    return VerificationResult(searched_at, tuple(verificados), tuple(descartados))


async def library_dois_of(session: Any, project_id: Any, candidates: Iterable[Candidate]) -> Set[str]:
    """DOI de `candidates` que el proyecto ya tiene en `library_documents` (mismo proyecto)."""
    from app.platform import library

    dois = {d for d in (_declared_doi(c)[0] for c in candidates) if d}
    return {d for d in dois if await library.find_by_doi(session, project_id, d) is not None}


def library_fields(verified: VerifiedCandidate) -> Dict[str, Any]:
    """Campos de `library_documents` para un candidato verificado (`curation_status='candidate'`)."""
    c = verified.candidate
    return {
        "doi": verified.doi, "title": c.title, "authors": list(c.authors), "year": c.year,
        "journal": c.journal, "abstract": c.abstract, "url": c.url,
        "open_access_url": c.open_access_url, "source_id": c.source_id, "source_db": c.source_db,
        "curation_status": "candidate", "verified": True,
        "verification_method": verified.verification_method, "verified_at": verified.verified_at,
    }


async def add_candidate_to_library(session: Any, project_id: Any, verified: VerifiedCandidate,
                                   *, added_by: Any = None) -> Any:
    """Guarda un candidato verificado como `candidate` en la biblioteca del proyecto.

    Un DOI repetido en el proyecto levanta `library.DuplicateDocumentError`. Sin API: la
    curación (aceptar, descartar, «imprescindible») es T22.8.
    """
    from app.platform import library

    return await library.add_document(session, project_id, added_by=added_by,
                                      **library_fields(verified))
