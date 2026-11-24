"""Biblioteca de investigación del proyecto (SPEC-034 / T22.3 / AC3).

Un documento de la biblioteca es lo que el Investigador puede citar: un candidato
que el autor aceptó, o un PDF que subió a mano. La fila guarda los **metadatos
bibliográficos** (DOI, autores, año, revista, base de origen) que el RAG por sí
solo no tenía, y el **estado de verificación** que exige ADR-0011: un documento sin
DOI verificado puede consultarse como contexto, pero no entra en `sources` ni en
Referencias, y no hay excepción para «documento interno».

Decisiones de esquema:

* Estados como `String` + `CHECK`, no como enum nativo de Postgres: añadir una
  etiqueta a un enum nativo exige `ALTER TYPE` fuera de transacción (ver la
  migración 0002) y aquí los valores aún pueden crecer.
* Unicidad del DOI **por proyecto** (`UniqueConstraint(project_id, doi)`). Con DOI
  nulo no hay unicidad: SQL trata cada `NULL` como distinto en SQLite y en
  Postgres, así que varios documentos «sin verificar» conviven. El DOI se guarda
  **normalizado** (minúsculas, sin prefijo de URL), por eso `10.1/ABC` y
  `https://doi.org/10.1/abc` chocan como deben.
"""
from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, JSON,
    String, Text, UniqueConstraint, UUID as SA_UUID, false,
)
from sqlalchemy.orm import validates

from app.core.database import Base


class SourceDB(str, Enum):
    """Base bibliográfica de la que viene el documento (AC1, AC3)."""

    OPENALEX = "openalex"
    CROSSREF = "crossref"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    ARXIV = "arxiv"
    PUBMED = "pubmed"
    MANUAL = "manual"


class TextStatus(str, Enum):
    """Qué texto hay detrás del documento (AC11)."""

    FULL_TEXT = "full_text"
    ABSTRACT_ONLY = "abstract_only"


class CurationStatus(str, Enum):
    """Decisión del autor sobre un documento (AC3)."""

    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    DISCARDED = "discarded"


class VerificationMethod(str, Enum):
    """Cómo se verificó el DOI (AC4, AC5)."""

    DOI_RESOLVED = "doi_resolved"
    AUTHOR_SUPPLIED = "author_supplied"


def _values(enum_cls) -> str:
    return ", ".join(f"'{m.value}'" for m in enum_cls)


_DOI_PREFIXES = (
    "https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:",
)


def normalize_doi(doi: str | None) -> str | None:
    """DOI canónico: minúsculas, sin espacios ni prefijo de URL/`doi:`. Vacío → `None`."""
    if doi is None:
        return None
    value = doi.strip().lower()
    for prefix in _DOI_PREFIXES:
        if value.startswith(prefix):
            value = value[len(prefix):].strip()
            break
    return value or None


def _check_enum(value, enum_cls, field: str):
    if value is None:
        return value
    raw = value.value if isinstance(value, enum_cls) else value
    if raw not in {m.value for m in enum_cls}:
        raise ValueError(f"{field} inválido: {value!r}")
    return raw


class LibraryDocumentModel(Base):
    __tablename__ = "library_documents"
    __table_args__ = (
        UniqueConstraint("project_id", "doi", name="uq_library_documents_project_doi"),
        Index("ix_library_documents_project_curation", "project_id", "curation_status"),
        CheckConstraint(f"source_db IN ({_values(SourceDB)})", name="ck_library_documents_source_db"),
        CheckConstraint(f"text_status IN ({_values(TextStatus)})", name="ck_library_documents_text_status"),
        CheckConstraint(
            f"curation_status IN ({_values(CurationStatus)})", name="ck_library_documents_curation_status"
        ),
        CheckConstraint(
            "verification_method IS NULL OR verification_method IN "
            f"({_values(VerificationMethod)})",
            name="ck_library_documents_verification_method",
        ),
        # ADR-0011: «verificado» sin DOI, sin método o sin fecha no puede existir.
        CheckConstraint(
            "verified = false OR (doi IS NOT NULL AND verification_method IS NOT NULL "
            "AND verified_at IS NOT NULL)",
            name="ck_library_documents_verified_has_evidence",
        ),
        # Que `author_supplied` registre quién (AC4) lo exige `library.mark_verified`, no un
        # CHECK: `verified_by` es `ON DELETE SET NULL` y borrar al usuario no puede fallar.
        # ADR-0013: «aportado por el autor» es la clase de un documento SIN identificador. Un DOI
        # declarado que no resuelve no se «lava» con la declaración: o se corrige o se quita.
        CheckConstraint(
            "author_provided = false OR (doi IS NULL AND author_provided_at IS NOT NULL)",
            name="ck_library_documents_author_provided_no_doi",
        ),
        CheckConstraint(
            "must_cite = false OR curation_status = 'accepted'",
            name="ck_library_documents_must_cite_accepted",
        ),
    )

    id = Column(SA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    # Aislamiento por proyecto (T8.5): la biblioteca no cruza proyectos.
    project_id = Column(
        SA_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    #: Identidad del documento en el RAG (payload de Qdrant). Nulo mientras solo
    #: hay resumen/metadatos y aún no se ha indexado texto.
    doc_id = Column(String(128), index=True)

    #: DOI normalizado (`normalize_doi`); único por proyecto cuando no es nulo.
    doi = Column(String(255))
    title = Column(Text, nullable=False)
    #: Lista de nombres, en el orden de la fuente.
    authors = Column(JSON, nullable=False, default=list)
    year = Column(Integer)
    journal = Column(String(512))
    #: Resumen que informa la base; es el texto de un documento `abstract_only`.
    abstract = Column(Text)
    #: Enlace al registro y, si la base lo informa, al PDF de acceso abierto (T22.10).
    url = Column(String(2048))
    open_access_url = Column(String(2048))
    #: Identificador del registro en `source_db` (id de OpenAlex, PMID, arXiv id…).
    source_id = Column(String(255))

    source_db = Column(String(32), nullable=False, default=SourceDB.MANUAL.value)
    text_status = Column(String(16), nullable=False, default=TextStatus.ABSTRACT_ONLY.value)
    curation_status = Column(
        String(16), nullable=False, default=CurationStatus.CANDIDATE.value, index=True
    )
    #: «Imprescindible» (AC3): el autor exige que el texto lo cite.
    must_cite = Column(Boolean, nullable=False, default=False)

    #: Verificación del DOI (ADR-0011). `verified_by` es nulo cuando verificó el
    #: sistema; con `author_supplied` registra quién aportó el DOI (AC4).
    verified = Column(Boolean, nullable=False, default=False, index=True)
    verification_method = Column(String(24))
    verified_at = Column(DateTime)
    verified_by = Column(SA_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    #: Declaración «aportado por el autor» (ADR-0013 / AC14): la hace una persona, nunca el
    #: sistema ni el modelo, y es reversible. Registra quién y cuándo; `author_provided_by` es
    #: `ON DELETE SET NULL` como `verified_by`, así que `library.declare_author_provided` es quien
    #: exige la persona, no un CHECK.
    author_provided = Column(Boolean, nullable=False, default=False, server_default=false())
    author_provided_at = Column(DateTime)
    author_provided_by = Column(SA_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    added_by = Column(SA_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    @validates("doi")
    def _normalize_doi(self, _key, value):
        return normalize_doi(value)

    @validates("source_db")
    def _validate_source_db(self, _key, value):
        return _check_enum(value, SourceDB, "source_db")

    @validates("text_status")
    def _validate_text_status(self, _key, value):
        return _check_enum(value, TextStatus, "text_status")

    @validates("curation_status")
    def _validate_curation_status(self, _key, value):
        return _check_enum(value, CurationStatus, "curation_status")

    @validates("verification_method")
    def _validate_verification_method(self, _key, value):
        return _check_enum(value, VerificationMethod, "verification_method")
