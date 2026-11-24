"""Ficha de biblioteca de un PDF subido a mano y edición de sus metadatos (SPEC-034 / T22.4 / AC4).

Al indexar un documento, el sistema crea su ficha en `library_documents` y **intenta**
resolver su DOI por título y autores con el mismo resolver que la compuerta de publicación
(`literature.verification.verify_candidates`, que sale por `safe_get`). Si resuelve y
coincide, la ficha queda `verified` con `doi_resolved`. Si no, queda **sin verificar**
—visible y editable— y `library.is_citable` la deja fuera de `sources` y de Referencias
hasta que el autor aporte el DOI (`author_supplied`, con quién y cuándo, ADR-0011).

Falla cerrada: que el resolver no responda **nunca** verifica, y tampoco impide indexar el
documento (la indexación ya ocurrió; la ficha queda sin verificar y se puede reintentar o
editar). Este módulo no habla con el RAG: quien llama decide la sesión.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.library_document import (
    CurationStatus, LibraryDocumentModel, SourceDB, TextStatus, VerificationMethod, normalize_doi,
)
from app.platform import library
from app.platform.capabilities.literature.models import Candidate
from app.platform.capabilities.literature.verification import verify_candidates
from app.platform.publication_gate.reference_resolver import ResolverConfig

logger = logging.getLogger(__name__)

#: Resultado de intentar resolver el DOI al subir.
RESOLVED = "resolved"
UNRESOLVED = "unresolved"
UNAVAILABLE = "unavailable"
NO_METADATA = "no_metadata"
DUPLICATE_DOI = "duplicate_doi"

#: Una subida no debe colgarse minutos esperando a Crossref: menos reintentos y tope total.
UPLOAD_RESOLVER = ResolverConfig(retries=1, timeout_s=8.0, max_total_s=30.0)


def split_authors(authors: Any) -> list[str]:
    """Autores como lista; acepta la cadena que extrae `extract_doc_metadata` o una lista."""
    if isinstance(authors, str):
        partes = re.split(r"\s*(?:;|,|\band\b|\by\b)\s*", authors)
    else:
        partes = [str(a) for a in (authors or [])]
    return [p.strip() for p in partes if p and p.strip()]


def _title_from(filename: str, title: str) -> str:
    return (title or "").strip() or Path(filename or "documento").stem or "documento"


async def register_uploaded_document(
    session: AsyncSession,
    project_id: UUID,
    *,
    doc_id: str,
    filename: str,
    title: str = "",
    authors: Any = "",
    added_by: UUID | None = None,
    resolver: ResolverConfig | None = None,
    fetch: Any = None,
) -> Dict[str, Any]:
    """Crea la ficha del documento subido e intenta verificar su DOI.

    Devuelve `{"document": <ficha>, "resolution": <estado>, "detail": <texto>}`. La ficha
    se crea siempre `accepted` (el autor la subió a propósito) y **sin verificar**; solo
    se verifica si el resolver encuentra un registro que coincide.
    """
    lista = split_authors(authors)
    doc = await library.add_document(
        session, project_id, added_by=added_by,
        doc_id=doc_id, title=_title_from(filename, title), authors=lista,
        source_db=SourceDB.MANUAL.value, text_status=TextStatus.FULL_TEXT.value,
        curation_status=CurationStatus.ACCEPTED.value,
    )
    if not (title or "").strip() or not lista:
        return {"document": doc, "resolution": NO_METADATA,
                "detail": "faltan título o autores para buscar el DOI; aporta el DOI a mano"}
    return await attempt_resolution(session, project_id, doc, resolver=resolver, fetch=fetch)


async def attempt_resolution(
    session: AsyncSession, project_id: UUID, doc: LibraryDocumentModel,
    *, resolver: ResolverConfig | None = None, fetch: Any = None,
) -> Dict[str, Any]:
    """Busca el DOI de la ficha por título y autores; verifica solo si el registro coincide."""
    candidato = Candidate(
        title=doc.title, source_db=SourceDB.MANUAL.value, authors=tuple(doc.authors or ()),
        year=doc.year, journal=doc.journal,
    )
    try:
        resultado = await verify_candidates(
            [candidato], datetime.utcnow(), resolver=resolver or UPLOAD_RESOLVER, fetch=fetch,
        )
    except Exception as error:  # falla cerrada: nunca verifica, tampoco rompe la subida
        logger.exception("library_upload: error resolviendo el DOI de %s", doc.id)
        return {"document": doc, "resolution": UNAVAILABLE,
                "detail": f"{type(error).__name__}: {error}"}

    if not resultado.verified:
        descartado = resultado.discarded[0] if resultado.discarded else None
        estado = UNAVAILABLE if descartado and descartado.not_verified else UNRESOLVED
        return {"document": doc, "resolution": estado,
                "detail": descartado.detail if descartado else "sin resultado"}

    v = resultado.verified[0]
    try:
        # Metadatos que el registro aporta y la ficha no tenía (no pisa lo que ya había).
        if doc.year is None and v.candidate.year:
            doc.year = v.candidate.year
        if not doc.journal and v.candidate.journal:
            doc.journal = v.candidate.journal
        doc = await library.mark_verified(
            session, project_id, doc.id, VerificationMethod.DOI_RESOLVED, doi=v.doi,
        )
    except library.DuplicateDocumentError:
        await session.rollback()
        await session.refresh(doc)
        return {"document": doc, "resolution": DUPLICATE_DOI,
                "detail": f"el DOI {v.doi} ya está en la biblioteca del proyecto"}
    return {"document": doc, "resolution": RESOLVED, "detail": v.doi}


async def update_metadata(
    session: AsyncSession,
    project_id: UUID,
    document_id: UUID,
    changes: Dict[str, Any],
    *,
    user_id: UUID,
) -> Optional[LibraryDocumentModel]:
    """Edita los metadatos de una ficha; un DOI nuevo lo aporta el autor (`author_supplied`).

    `changes` puede traer `title`, `authors`, `year`, `journal` y `doi`. Un DOI distinto del
    actual verifica la ficha con `author_supplied`, registrando `verified_by=user_id` y
    `verified_at`; vaciarlo (`""`/`None`) **retira** la verificación. Si el DOI ya lo tiene
    otro documento del proyecto, `DuplicateDocumentError` y no se cambia nada.
    Devuelve `None` si la ficha no existe en el proyecto.
    """
    doc = await library.get_document(session, project_id, document_id)
    if doc is None:
        return None
    nuevo_doi = None
    cambia_doi = False
    if "doi" in changes:
        nuevo_doi = normalize_doi(changes["doi"])
        cambia_doi = nuevo_doi != doc.doi
        if cambia_doi and nuevo_doi is not None:
            otro = await library.find_by_doi(session, project_id, nuevo_doi)
            if otro is not None and otro.id != doc.id:
                raise library.DuplicateDocumentError(nuevo_doi)

    if "title" in changes:
        titulo = (changes["title"] or "").strip()
        if not titulo:
            raise ValueError("el título no puede quedar vacío")
        doc.title = titulo
    if "authors" in changes:
        doc.authors = split_authors(changes["authors"])
    if "year" in changes:
        doc.year = changes["year"]
    if "journal" in changes:
        doc.journal = (changes["journal"] or "").strip() or None

    if cambia_doi and nuevo_doi is None:
        doc.doi = None
        doc.verified = False
        doc.verification_method = None
        doc.verified_at = None
        doc.verified_by = None
    await session.commit()
    if cambia_doi and nuevo_doi is not None:
        return await library.mark_verified(
            session, project_id, document_id, VerificationMethod.AUTHOR_SUPPLIED,
            verified_by=user_id, doi=nuevo_doi,
        )
    await session.refresh(doc)
    return doc


def document_view(doc: LibraryDocumentModel) -> Dict[str, Any]:
    """La ficha como la ve el autor: metadatos, estado de verificación y si puede citarse."""
    return {
        "id": str(doc.id), "doc_id": doc.doc_id, "doi": doc.doi, "title": doc.title,
        "authors": list(doc.authors or []), "year": doc.year, "journal": doc.journal,
        "source_db": doc.source_db, "text_status": doc.text_status,
        "curation_status": doc.curation_status, "must_cite": bool(doc.must_cite),
        "verified": bool(doc.verified), "verification_method": doc.verification_method,
        "verified_at": doc.verified_at.isoformat() + "Z" if doc.verified_at else None,
        "verified_by": str(doc.verified_by) if doc.verified_by else None,
        "citable": library.is_citable(doc),
        # Clase citable (ADR-0013): «identified», «author_provided» o `None` (solo contexto).
        "source_class": library.source_class(doc),
        "author_provided": bool(doc.author_provided),
        "author_provided_at": doc.author_provided_at.isoformat() + "Z"
        if doc.author_provided_at else None,
        "author_provided_by": str(doc.author_provided_by) if doc.author_provided_by else None,
    }
