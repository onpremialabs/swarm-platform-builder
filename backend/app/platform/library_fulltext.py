"""Texto completo de una ficha de biblioteca: PDF de acceso abierto o subido a mano (SPEC-034 / T22.10 / AC11).

Al **aceptar** un candidato cuya base informa una URL de acceso abierto, se intenta
descargar el PDF y se indexa; la ficha queda `text_status=full_text`. Si no hay URL o algo
falla (red, destino bloqueado, no es un PDF, es demasiado grande, no tiene texto, el índice
no responde), la ficha se acepta igualmente como `abstract_only` («solo resumen»): la
aceptación **nunca** falla por esto. Subir el PDF después la pasa a `full_text`.

Reglas que no se negocian:

* La descarga sale **solo** por `egress.safe_get` (`quien="literature_discovery"`): IP
  resuelta, redirecciones revalidadas. Sin cliente HTTP propio.
* **Solo** se usa `open_access_url`, la que informa la base. No se prueba ninguna otra URL
  (la del registro, `doi.org`, espejos) ni se elude un paywall: si la URL de acceso abierto
  devuelve una página en vez de un PDF, es un fallo y la ficha queda en «solo resumen».
* El contenido se valida como una subida manual (`uploads.validate_upload`: extensión y
  *magic bytes*), más tipo de contenido y tamaño.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.library_document import LibraryDocumentModel, TextStatus
from app.platform import egress, library
from app.platform.project_context import ProjectContext

logger = logging.getLogger(__name__)

QUIEN = "literature_discovery"
#: Mismo tope que la subida manual.
MAX_PDF_BYTES = 10 * 1024 * 1024
_PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf", "application/octet-stream",
                      "binary/octet-stream"}

#: Resultados de `accept_with_fulltext` (`fulltext`).
FULL_TEXT = "full_text"
NO_OPEN_ACCESS_URL = "no_open_access_url"
ALREADY_FULL_TEXT = "already_full_text"
FAILED = "download_failed"


class FulltextError(Exception):
    """No se pudo obtener o indexar el texto completo; el mensaje es el motivo legible."""


async def fetch_open_access_pdf(url: str) -> bytes:
    """Descarga el PDF de acceso abierto por `safe_get` y lo valida. Levanta `FulltextError`."""
    try:
        resp = await egress.safe_get(url, quien=QUIEN, timeout=30.0,
                                     headers={"Accept": "application/pdf"})
    except Exception as error:  # egreso bloqueado, red, redirecciones de más…
        raise FulltextError(f"descarga fallida: {type(error).__name__}") from error
    if getattr(resp, "status_code", 0) != 200:
        raise FulltextError(f"la URL respondió {getattr(resp, 'status_code', '?')}")
    headers = getattr(resp, "headers", None) or {}
    tipo = str(headers.get("content-type", "")).split(";")[0].strip().lower()
    if tipo and tipo not in _PDF_CONTENT_TYPES:
        raise FulltextError(f"la URL no sirve un PDF (tipo {tipo})")
    declarado = str(headers.get("content-length", "")).strip()
    if declarado.isdigit() and int(declarado) > MAX_PDF_BYTES:
        raise FulltextError("el PDF supera el tamaño máximo")
    raw = getattr(resp, "content", b"") or b""
    if len(raw) > MAX_PDF_BYTES:
        raise FulltextError("el PDF supera el tamaño máximo")
    from fastapi import HTTPException

    from app.platform.uploads import validate_upload
    try:
        validate_upload("open-access.pdf", raw, {".pdf"})
    except HTTPException as error:
        raise FulltextError("el contenido descargado no es un PDF válido") from error
    return raw


async def index_pdf(
    project: ProjectContext, raw: bytes, filename: str, *, title: str = "", authors: Any = "",
    collection: Optional[str] = None,
) -> Tuple[str, int]:
    """Extrae, trocea e indexa un PDF en la biblioteca del proyecto. Devuelve `(doc_id, chunks)`.

    Levanta `FulltextError` si no hay texto extraíble o el índice no lo acepta.
    """
    from app.core.config import settings
    from app.platform.capabilities import rag

    texto = rag.extract_text(filename, raw)
    if not texto.strip():
        raise FulltextError("no se pudo extraer texto del PDF")
    col = project.collection(collection or settings.QDRANT_COLLECTION)
    doc_id = str(uuid.uuid4())
    chunks = rag.chunk_text(texto, chunk_size=getattr(settings, "RAG_CHUNK_SIZE", 500), overlap=50)
    autores = authors if isinstance(authors, str) else "; ".join(authors or [])
    try:
        await rag.ensure_collection(settings.QDRANT_URL, col, rag.embed_vector_size(),
                                    settings.QDRANT_API_KEY)
        n = await rag.upsert_chunks(
            qdrant_url=settings.QDRANT_URL, collection=col, doc_id=doc_id,
            agent_name="__library__", filename=filename, chunks=chunks,
            ollama_base_url=settings.OLLAMA_BASE_URL, embedding_model=settings.OLLAMA_EMBED_MODEL,
            vector_size=rag.embed_vector_size(), api_key=settings.QDRANT_API_KEY,
            doc_title=title, doc_authors=autores,
        )
    except Exception as error:
        raise FulltextError(f"no se pudo indexar el PDF: {type(error).__name__}") from error
    if n <= 0:
        raise FulltextError("no se pudo indexar el PDF")
    return doc_id, n


def _filename(doc: LibraryDocumentModel) -> str:
    base = (doc.doi or doc.source_id or str(doc.id)).replace("/", "_").replace(":", "_")
    return f"{base}.pdf"


async def accept_with_fulltext(
    session: AsyncSession, project: ProjectContext, document_id: UUID, *, must_cite: bool = False,
    fetch_pdf: Any = None, indexer: Any = None,
) -> Optional[Dict[str, Any]]:
    """Acepta un candidato e intenta dejarlo en `full_text`. `None` si la ficha no existe.

    Devuelve `{"document", "fulltext": <resultado>, "detail": <motivo>}`. Aceptar se confirma
    **antes** de intentar la descarga: si ésta o la indexación fallan, la ficha ya está
    aceptada y `abstract_only`. Solo se intenta al pasar a aceptado (marcar «imprescindible»
    sobre una ficha ya aceptada no vuelve a descargar).
    """
    previa = await library.get_document(session, project.project_id, document_id)
    if previa is None:
        return None
    ya_aceptada = previa.curation_status == "accepted"
    doc = await library.set_curation(session, project.project_id, document_id, "accepted",
                                     must_cite=must_cite)
    if doc.text_status == TextStatus.FULL_TEXT.value:
        return {"document": doc, "fulltext": ALREADY_FULL_TEXT, "detail": ""}
    if not doc.open_access_url:
        return {"document": doc, "fulltext": NO_OPEN_ACCESS_URL,
                "detail": "la base no informa un PDF de acceso abierto; sube el PDF para tener el texto"}
    if ya_aceptada:
        return {"document": doc, "fulltext": FAILED, "detail": "sin reintento: sube el PDF"}
    try:
        raw = await (fetch_pdf or fetch_open_access_pdf)(doc.open_access_url)
        doc_id, _ = await (indexer or index_pdf)(
            project, raw, _filename(doc), title=doc.title, authors=list(doc.authors or []))
    except FulltextError as error:
        logger.info("library_fulltext: %s queda en solo resumen: %s", doc.id, error)
        return {"document": doc, "fulltext": FAILED, "detail": str(error)}
    except Exception as error:  # nada de esto puede romper la aceptación
        logger.exception("library_fulltext: error inesperado con %s", doc.id)
        return {"document": doc, "fulltext": FAILED, "detail": type(error).__name__}
    doc = await library.set_text_status(session, project.project_id, doc.id,
                                        TextStatus.FULL_TEXT, doc_id=doc_id)
    return {"document": doc, "fulltext": FULL_TEXT, "detail": ""}
