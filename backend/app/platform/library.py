"""Acceso a la biblioteca de investigación y al registro de búsqueda (SPEC-034 / T22.3).

Capa de persistencia mínima sobre `library_documents` y `search_logs`. **No** habla
con bases externas (T22.1), no verifica contra Crossref (T22.2) ni expone API
(T22.8): recibe datos ya resueltos y los guarda respetando las invariantes de
ADR-0011. Todas las funciones exigen el `project_id`: la biblioteca no cruza
proyectos.
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.library_document import (
    CurationStatus,
    LibraryDocumentModel,
    TextStatus,
    VerificationMethod,
    normalize_doi,
)
from app.models.search_log import SEARCH_STATUSES, SearchLogModel


class DuplicateDocumentError(Exception):
    """Ya hay un documento con ese DOI en el proyecto."""


async def find_by_doi(
    session: AsyncSession, project_id: UUID, doi: str | None
) -> LibraryDocumentModel | None:
    doi = normalize_doi(doi)
    if doi is None:
        return None
    return await session.scalar(
        select(LibraryDocumentModel).where(
            LibraryDocumentModel.project_id == project_id, LibraryDocumentModel.doi == doi
        )
    )


async def add_document(
    session: AsyncSession, project_id: UUID, *, added_by: UUID | None = None, **fields
) -> LibraryDocumentModel:
    """Añade un documento al proyecto. Un DOI repetido en el proyecto → `DuplicateDocumentError`."""
    if await find_by_doi(session, project_id, fields.get("doi")) is not None:
        raise DuplicateDocumentError(fields.get("doi"))
    doc = LibraryDocumentModel(project_id=project_id, added_by=added_by, **fields)
    session.add(doc)
    try:
        await session.commit()
    except IntegrityError as exc:  # carrera con otra inserción del mismo DOI
        await session.rollback()
        raise DuplicateDocumentError(fields.get("doi")) from exc
    await session.refresh(doc)
    return doc


async def get_document(
    session: AsyncSession, project_id: UUID, document_id: UUID
) -> LibraryDocumentModel | None:
    return await session.scalar(
        select(LibraryDocumentModel).where(
            LibraryDocumentModel.project_id == project_id, LibraryDocumentModel.id == document_id
        )
    )


async def list_documents(
    session: AsyncSession,
    project_id: UUID,
    *,
    curation_status: CurationStatus | str | None = None,
    verified: bool | None = None,
) -> list[LibraryDocumentModel]:
    query = select(LibraryDocumentModel).where(LibraryDocumentModel.project_id == project_id)
    if curation_status is not None:
        query = query.where(
            LibraryDocumentModel.curation_status == CurationStatus(curation_status).value
        )
    if verified is not None:
        query = query.where(LibraryDocumentModel.verified.is_(verified))
    result = await session.scalars(query.order_by(LibraryDocumentModel.created_at))
    return list(result)


async def citable_documents(session: AsyncSession, project_id: UUID) -> list[LibraryDocumentModel]:
    """Lo que puede entrar en `sources` y Referencias (AC5): aceptado **y** con DOI verificado."""
    return await list_documents(
        session, project_id, curation_status=CurationStatus.ACCEPTED, verified=True
    )


async def set_curation(
    session: AsyncSession,
    project_id: UUID,
    document_id: UUID,
    status: CurationStatus | str,
    *,
    must_cite: bool = False,
) -> LibraryDocumentModel | None:
    """Acepta, descarta o marca «imprescindible» (AC3). Descartar retira la marca."""
    doc = await get_document(session, project_id, document_id)
    if doc is None:
        return None
    status = CurationStatus(status)
    doc.curation_status = status.value
    doc.must_cite = bool(must_cite) and status is CurationStatus.ACCEPTED
    await session.commit()
    await session.refresh(doc)
    return doc


async def mark_verified(
    session: AsyncSession,
    project_id: UUID,
    document_id: UUID,
    method: VerificationMethod | str,
    *,
    verified_by: UUID | None = None,
    doi: str | None = None,
) -> LibraryDocumentModel | None:
    """Registra la verificación del DOI (ADR-0011).

    `author_supplied` exige `verified_by` —quién aportó el DOI— y fija `doi` si se
    pasa. Sin DOI no hay verificación posible.
    """
    doc = await get_document(session, project_id, document_id)
    if doc is None:
        return None
    method = VerificationMethod(method)
    if method is VerificationMethod.AUTHOR_SUPPLIED and verified_by is None:
        raise ValueError("aportar el DOI a mano debe registrar quién lo aportó")
    if doi is not None:
        other = await find_by_doi(session, project_id, doi)
        if other is not None and other.id != doc.id:
            raise DuplicateDocumentError(normalize_doi(doi))
        doc.doi = doi
    if not doc.doi:
        raise ValueError("un documento sin DOI no puede marcarse como verificado")
    doc.verified = True
    doc.verification_method = method.value
    doc.verified_at = datetime.utcnow()
    doc.verified_by = verified_by
    await session.commit()
    await session.refresh(doc)
    return doc


async def set_text_status(
    session: AsyncSession, project_id: UUID, document_id: UUID, text_status: TextStatus | str,
    *, doc_id: str | None = None,
) -> LibraryDocumentModel | None:
    """`abstract_only` → `full_text` cuando se indexa el PDF (AC11)."""
    doc = await get_document(session, project_id, document_id)
    if doc is None:
        return None
    doc.text_status = TextStatus(text_status).value
    if doc_id is not None:
        doc.doc_id = doc_id
    await session.commit()
    await session.refresh(doc)
    return doc


async def record_search(
    session: AsyncSession,
    project_id: UUID,
    *,
    query: str,
    sources: list[str],
    filters: dict | None = None,
    result_count: int = 0,
    verified_count: int = 0,
    per_source: dict | None = None,
    discarded: dict | None = None,
    status: str = "completed",
    article_id: UUID | None = None,
    user_id: UUID | None = None,
    searched_at: datetime | None = None,
) -> SearchLogModel:
    """Persiste el registro de una búsqueda terminada (AC6). `searched_at` es la fecha de corte."""
    if status not in SEARCH_STATUSES:
        raise ValueError(f"status inválido: {status!r}")
    log = SearchLogModel(
        project_id=project_id,
        article_id=article_id,
        user_id=user_id,
        query=query,
        sources=list(sources),
        filters=dict(filters or {}),
        result_count=result_count,
        verified_count=verified_count,
        per_source=dict(per_source or {}),
        discarded=dict(discarded or {}),
        status=status,
        searched_at=searched_at or datetime.utcnow(),
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log


async def list_searches(
    session: AsyncSession, project_id: UUID, *, article_id: UUID | None = None
) -> list[SearchLogModel]:
    query = select(SearchLogModel).where(SearchLogModel.project_id == project_id)
    if article_id is not None:
        query = query.where(SearchLogModel.article_id == article_id)
    return list(await session.scalars(query.order_by(SearchLogModel.searched_at)))


#: Formato del registro de búsqueda exportado (SPEC-034 / T22.7 / AC6). Versionado:
#: un fichero guardado hoy tiene que seguir siendo legible cuando el registro gane
#: campos. Es una lista explícita —no «todas las columnas»— para que añadir una
#: columna al modelo no cambie lo que sale sin que alguien lo decida. No incluye
#: `user_id` ni nada que no sea cadena de búsqueda y metadatos de resultados.
SEARCH_RECORD_VERSION = 1
SEARCH_RECORD_FIELDS = (
    "id", "article_id", "query", "sources", "filters", "searched_at", "status",
    "result_count", "verified_count", "discarded", "per_source",
)


def search_record(log: SearchLogModel) -> dict:
    """El registro de una búsqueda en su forma estable (JSON-serializable).

    `searched_at` es UTC y sale con sufijo `Z`: la columna es ingenua y sin la marca
    un lector fuera de la plataforma no sabría en qué zona leerla.
    """
    registro = {
        "id": str(log.id),
        "article_id": str(log.article_id) if log.article_id else None,
        "query": log.query,
        "sources": list(log.sources or []),
        "filters": dict(log.filters or {}),
        "searched_at": log.searched_at.replace(microsecond=0).isoformat() + "Z"
        if log.searched_at else None,
        "status": log.status,
        "result_count": log.result_count,
        "verified_count": log.verified_count,
        "discarded": dict(log.discarded or {}),
        "per_source": dict(log.per_source or {}),
    }
    return {campo: registro[campo] for campo in SEARCH_RECORD_FIELDS}
