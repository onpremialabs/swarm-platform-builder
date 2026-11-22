"""Registro de búsqueda bibliográfica (SPEC-034 / T22.3 / AC6, AC2).

Una fila por búsqueda de descubrimiento, escrita al terminar: es lo que permite
reproducirla —qué bases, qué cadena, qué filtros, cuándo— y declararla en el
método del artículo. `searched_at` es además la **fecha de corte** de AC2: solo se
descartan candidatos con fecha de publicación posterior a ella.

Qué NO guarda, a propósito: el texto del manuscrito. `query` es la cadena que el
autor escribió para buscar, que es justo lo que se envía a terceros. Tampoco claves
de API ni cabeceras. Retención en `docs/governance/data-retention.md`.
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text,
    UUID as SA_UUID,
)

from app.core.database import Base

SEARCH_STATUSES = ("completed", "partial", "failed")


class SearchLogModel(Base):
    __tablename__ = "search_logs"
    __table_args__ = (
        Index("ix_search_logs_project_searched", "project_id", "searched_at"),
        CheckConstraint("status IN ('completed', 'partial', 'failed')", name="ck_search_logs_status"),
        CheckConstraint("result_count >= 0 AND verified_count >= 0", name="ck_search_logs_counts"),
    )

    id = Column(SA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id = Column(
        SA_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # `SET NULL`: borrar el artículo no debe llevarse el rastro del proyecto.
    article_id = Column(SA_UUID(as_uuid=True), ForeignKey("articles.id", ondelete="SET NULL"), index=True)
    user_id = Column(SA_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    #: Cadena de búsqueda tal cual la escribió el autor.
    query = Column(Text, nullable=False)
    #: Bases consultadas (`SourceDB`), en el orden en que se consultaron.
    sources = Column(JSON, nullable=False, default=list)
    #: Filtros aplicados (años, tipo de documento, idioma…).
    filters = Column(JSON, nullable=False, default=dict)

    #: Candidatos devueltos por las bases, antes de verificar.
    result_count = Column(Integer, nullable=False, default=0)
    #: Los que superaron la verificación y se ofrecieron al autor (AC2).
    verified_count = Column(Integer, nullable=False, default=0)
    #: Por base, para reproducir: `{"openalex": {"returned": 25, "error": null}}`.
    per_source = Column(JSON, nullable=False, default=dict)
    #: Por qué se descartó lo descartado: `{"unresolved": 3, "duplicate": 2, "future_date": 1}`.
    discarded = Column(JSON, nullable=False, default=dict)

    #: `completed`, `partial` (alguna base falló o limitó) o `failed` (AC10).
    status = Column(String(16), nullable=False, default="completed")
    #: Fecha de la búsqueda = fecha de corte de AC2.
    searched_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
