"""Tipos del descubrimiento de literatura (SPEC-034 / T22.1).

Un **candidato** es lo que una base bibliográfica dice que existe. Aún **no** es una
fuente: verificar que resuelve por DOI, descartar duplicados y fechas futuras es
T22.2, y por eso `Candidate.verified` es siempre `False` y no se puede cambiar al
construirlo (ADR-0011: nada se acepta por el simple hecho de que una API lo devuelva).

Los nombres de campo coinciden con las columnas de `library_documents`
(`app/models/library_document.py`) para que aceptar un candidato sea copiar campos.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

#: Bases soportadas; coinciden con `SourceDB` (hay un test que lo comprueba).
OPENALEX = "openalex"
CROSSREF = "crossref"
SEMANTIC_SCHOLAR = "semantic_scholar"
ARXIV = "arxiv"
PUBMED = "pubmed"

KNOWN_SOURCES: Tuple[str, ...] = (OPENALEX, CROSSREF, SEMANTIC_SCHOLAR, ARXIV, PUBMED)
#: Lo que se consulta si el proyecto no dice otra cosa (SPEC-034, Clarifications).
DEFAULT_SOURCES: Tuple[str, ...] = (OPENALEX, CROSSREF)

#: Una consulta es una cadena de búsqueda, no un texto: más allá de esto es casi seguro
#: que alguien pasó un fragmento del manuscrito, y eso no debe salir a terceros.
MAX_QUERY_CHARS = 300

_DOI_PREFIX = re.compile(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)


def normalize_doi(doi: Optional[str]) -> Optional[str]:
    """DOI en minúsculas y sin prefijo de URL/`doi:`; vacío -> `None`.

    Mismo criterio que `library_document.normalize_doi` y que el resolver de la compuerta
    (hay un test de paridad). Se repite aquí en tres líneas en vez de importar la compuerta:
    la capacidad no debe depender de ella.
    """
    value = _DOI_PREFIX.sub("", (doi or "").strip()).strip().lower()
    return value or None


class LiteratureQueryError(ValueError):
    """La consulta no es una cadena de búsqueda aceptable (vacía o demasiado larga)."""


class UnknownSourceError(ValueError):
    """Se pidió una base que la capacidad no conoce."""


@dataclass(frozen=True)
class Candidate:
    """Candidato normalizado, **no verificado**."""

    title: str
    source_db: str
    source_id: Optional[str] = None
    doi: Optional[str] = None
    authors: Tuple[str, ...] = ()
    year: Optional[int] = None
    #: ISO tal y como la informa la base: `YYYY`, `YYYY-MM` o `YYYY-MM-DD`.
    publication_date: Optional[str] = None
    journal: Optional[str] = None
    abstract: Optional[str] = None
    url: Optional[str] = None
    open_access_url: Optional[str] = None
    #: Siempre `False` aquí: verificar es T22.2. `init=False` impide fabricar uno «verificado».
    verified: bool = field(default=False, init=False)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title, "authors": list(self.authors), "year": self.year,
            "publication_date": self.publication_date, "doi": self.doi,
            "source_db": self.source_db, "source_id": self.source_id,
            "journal": self.journal, "abstract": self.abstract, "url": self.url,
            "open_access_url": self.open_access_url, "verified": self.verified,
        }


def build_candidate(source_db: str, **campos: Any) -> Optional[Candidate]:
    """Construye un candidato o `None` si no cumple el mínimo (falla cerrada).

    El mínimo es **título** y **alguna identificación** (DOI o id de la base). Un
    registro sin eso no se puede resolver ni citar, así que no se ofrece.
    """
    titulo = " ".join(str(campos.get("title") or "").split())
    doi = normalize_doi(campos.get("doi"))
    source_id = str(campos["source_id"]).strip() if campos.get("source_id") else None
    if not titulo or not (doi or source_id):
        return None

    def texto(clave: str) -> Optional[str]:
        valor = " ".join(str(campos.get(clave) or "").split())
        return valor or None

    anio = campos.get("year")
    try:
        anio = int(anio) if anio is not None else None
    except (TypeError, ValueError):
        anio = None

    autores = tuple(a for a in (" ".join(str(x).split()) for x in campos.get("authors") or ()) if a)
    return Candidate(
        title=titulo, source_db=source_db, source_id=source_id, doi=doi, authors=autores,
        year=anio, publication_date=texto("publication_date"), journal=texto("journal"),
        abstract=texto("abstract"), url=texto("url"), open_access_url=texto("open_access_url"),
    )


@dataclass(frozen=True)
class Parsed:
    """Resultado de normalizar una respuesta: candidatos y cuántos registros se descartaron."""

    candidates: List[Candidate]
    dropped: int = 0


@dataclass(frozen=True)
class BaseReport:
    """Qué pasó con una base. Un fallo parcial **se ve**, nunca se traga (AC10)."""

    db: str
    #: `ok` | `failed` | `skipped` (p. ej. Semantic Scholar sin clave).
    status: str
    count: int = 0
    #: Registros sin título o sin identificación, descartados por falla cerrada.
    dropped: int = 0
    attempts: int = 0
    #: `timeout` | `rate_limited` | `http_error` | `invalid_response` | `network` |
    #: `blocked` | `missing_api_key`; vacío si fue bien.
    error_kind: str = ""
    message: str = ""


@dataclass(frozen=True)
class LiteratureResult:
    query: str
    candidates: List[Candidate]
    reports: Tuple[BaseReport, ...]

    @property
    def failed(self) -> List[BaseReport]:
        return [r for r in self.reports if r.status == "failed"]

    @property
    def skipped(self) -> List[BaseReport]:
        return [r for r in self.reports if r.status == "skipped"]

    @property
    def complete(self) -> bool:
        """`True` solo si **todas** las bases pedidas respondieron."""
        return all(r.status == "ok" for r in self.reports)

    @property
    def all_failed(self) -> bool:
        return bool(self.reports) and not any(r.status == "ok" for r in self.reports)
