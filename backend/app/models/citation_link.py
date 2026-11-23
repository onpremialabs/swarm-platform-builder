"""Mapa cita → fragmento, versionado con el texto (SPEC-035 / T23.2 / AC1, AC6).

Una fila por cita del texto: qué afirmación se apoya en qué fragmento concreto de
la biblioteca (documento, página, extracto y huella del extracto). Va ligada al
texto evaluado por su huella SHA-256 (`text_sha256`), igual que el informe de la
compuerta: una nueva versión del texto crea **otro** conjunto de filas y no
sobrescribe, así que se sabe qué se citó en cada versión. El mapa vigente de un
artículo es el de la huella que coincide con su cuerpo.

`status` lo fija quien evalúa (T23.3/T23.4); aquí nace `not_verified`, que es la
política de falla cerrada de ADR-0011. La confirmación manual del autor (AC6) es
aparte —`confirmed_by`/`confirmed_at`— y **no** pisa el veredicto automático: se
ven los dos.

Qué NO guarda: el texto completo del manuscrito. `claim` es la frase citada,
recortada, y `excerpt` el pasaje de la fuente, recortado. Retención en
`docs/governance/data-retention.md`.
"""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, UUID as SA_UUID,
)

from app.core.database import Base

#: `not_verified` = aún sin evaluar o sin fragmento (falla cerrada, AC2).
CITATION_STATUSES = ("not_verified", "supported", "partial", "unsupported")

CLAIM_MAX_CHARS = 1000
EXCERPT_MAX_CHARS = 2000


class CitationLinkModel(Base):
    __tablename__ = "citation_links"
    __table_args__ = (
        Index("ix_citation_links_article_text", "article_id", "text_sha256"),
        UniqueConstraint(
            "article_id", "text_sha256", "citation_key", "claim_index",
            name="uq_citation_links_version_citation",
        ),
        CheckConstraint(
            "status IN ('not_verified', 'supported', 'partial', 'unsupported')",
            name="ck_citation_links_status",
        ),
        CheckConstraint(
            "confirmed_by IS NULL OR confirmed_at IS NOT NULL",
            name="ck_citation_links_confirmation_dated",
        ),
    )

    id = Column(SA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    # `CASCADE`: sin el artículo, su mapa de citas no describe nada.
    article_id = Column(
        SA_UUID(as_uuid=True), ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # `SET NULL`, como la traza: purgar la ejecución no se lleva el mapa.
    run_id = Column(SA_UUID(as_uuid=True), ForeignKey("agent_runs.run_id", ondelete="SET NULL"))
    #: Huella SHA-256 del texto cuyas citas describe esta fila (la «versión»).
    text_sha256 = Column(String(64), nullable=False)

    #: Identificador de la cita tal como aparece en el texto (p. ej. el id de fragmento).
    citation_key = Column(String(128), nullable=False)
    #: Orden de la afirmación citada en el texto; distingue dos usos de la misma cita.
    claim_index = Column(Integer, nullable=False, default=0)
    #: Frase que lleva la cita, recortada.
    claim = Column(Text, nullable=False, default="")

    #: Documento de la biblioteca; nulo si la cita no tiene fragmento asociado (AC2).
    doc_id = Column(String(128), index=True)
    #: Página del fragmento; nulo si no se conoce (se degrada a «sección», SPEC-035 §5).
    page = Column(Integer)
    section = Column(String(255))
    #: Pasaje de la fuente, recortado.
    excerpt = Column(Text, nullable=False, default="")
    #: SHA-256 del extracto, para detectar que el fragmento indexado cambió.
    excerpt_sha256 = Column(String(64), nullable=False, default="")

    status = Column(String(16), nullable=False, default="not_verified")
    #: Justificación breve del veredicto (solape, juez…).
    rationale = Column(Text)

    #: Confirmación manual del autor (AC6): quién y cuándo.
    confirmed_by = Column(SA_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    confirmed_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class CitationLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    article_id: UUID
    text_sha256: str
    citation_key: str
    claim_index: int
    claim: str
    doc_id: str | None = None
    page: int | None = None
    section: str | None = None
    excerpt: str
    excerpt_sha256: str
    status: str
    rationale: str | None = None
    confirmed_by: UUID | None = None
    confirmed_at: datetime | None = None
    created_at: datetime
