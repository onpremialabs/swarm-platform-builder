"""Persistencia del mapa cita → fragmento (SPEC-035 / T23.2 / AC1, AC6).

Solo guarda y lee: **no** decide si una cita sustenta su frase (eso es la
compuerta, T23.3/T23.4) ni toca al Redactor. Quien extraiga las citas del borrador
—hoy o cuando T23.1 aterrice— entrega una lista de `CitationInput` y esto la
versiona con la huella del texto evaluado.

Reglas:

* **Versionado.** Cada fila lleva la huella SHA-256 del texto. Guardar el mapa de
  una huella ya existente lo *reemplaza* (reejecutar sobre el mismo texto es
  idempotente) pero **no toca** el de otras huellas: el historial de versiones se
  conserva. El mapa vigente es el de la huella del cuerpo actual.
* **Falla cerrada.** Una cita sin fragmento nace `not_verified` (ADR-0011).
* **Confirmación manual aparte.** Confirmar registra quién y cuándo, y no cambia
  `status`: el veredicto automático y el humano se ven por separado. Reemplazar el
  mapa de una huella **conserva** las confirmaciones de las citas que no cambiaron
  (misma cita, misma frase y mismo extracto).
"""
import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import ArticleModel
from app.models.citation_link import (
    CLAIM_MAX_CHARS, EXCERPT_MAX_CHARS, CitationLinkModel,
)
from app.platform.publication_gate.service import text_sha256


@dataclass
class CitationInput:
    """Una cita del texto con el fragmento al que apunta (si lo hay)."""

    citation_key: str
    claim: str = ""
    doc_id: Optional[str] = None
    page: Optional[int] = None
    section: Optional[str] = None
    excerpt: str = ""
    claim_index: Optional[int] = None  # por defecto, el orden de llegada


def excerpt_sha256(excerpt: Optional[str]) -> str:
    return hashlib.sha256((excerpt or "").encode("utf-8")).hexdigest()


async def save_citation_map(
    session: AsyncSession,
    article_id: UUID,
    text: Optional[str],
    citations: Iterable[CitationInput],
    *,
    run_id: Optional[UUID] = None,
) -> list[CitationLinkModel]:
    """Guarda el mapa de citas del `text` evaluado (sin hacer commit)."""
    version = text_sha256(text)

    previas = (await session.execute(
        select(CitationLinkModel).where(
            CitationLinkModel.article_id == article_id,
            CitationLinkModel.text_sha256 == version,
        )
    )).scalars().all()
    confirmadas = {
        (p.citation_key, p.claim, p.excerpt_sha256): (p.confirmed_by, p.confirmed_at)
        for p in previas if p.confirmed_at is not None
    }
    if previas:
        await session.execute(delete(CitationLinkModel).where(
            CitationLinkModel.article_id == article_id,
            CitationLinkModel.text_sha256 == version,
        ))
        await session.flush()

    filas: list[CitationLinkModel] = []
    vistos: set[tuple[str, int]] = set()
    for orden, c in enumerate(citations):
        indice = orden if c.claim_index is None else c.claim_index
        clave = (c.citation_key, indice)
        if clave in vistos:
            continue
        vistos.add(clave)
        claim = (c.claim or "")[:CLAIM_MAX_CHARS]
        extracto = (c.excerpt or "")[:EXCERPT_MAX_CHARS]
        huella = excerpt_sha256(extracto)
        quien, cuando = confirmadas.get((c.citation_key, claim, huella), (None, None))
        filas.append(CitationLinkModel(
            article_id=article_id, run_id=run_id, text_sha256=version,
            citation_key=c.citation_key, claim_index=indice, claim=claim,
            doc_id=c.doc_id, page=c.page, section=c.section,
            excerpt=extracto, excerpt_sha256=huella,
            status="not_verified", confirmed_by=quien, confirmed_at=cuando,
        ))
    session.add_all(filas)
    await session.flush()
    return filas


async def get_citation_map(
    session: AsyncSession, article_id: UUID, text_sha: str
) -> list[CitationLinkModel]:
    """Mapa de una versión concreta del texto, en orden de aparición."""
    result = await session.execute(
        select(CitationLinkModel)
        .where(CitationLinkModel.article_id == article_id,
               CitationLinkModel.text_sha256 == text_sha)
        .order_by(CitationLinkModel.claim_index, CitationLinkModel.citation_key)
    )
    return list(result.scalars().all())


async def current_citation_map(
    session: AsyncSession, article: ArticleModel
) -> list[CitationLinkModel]:
    """Mapa vigente: el de la huella del cuerpo actual (vacío si el texto cambió)."""
    return await get_citation_map(session, article.id, text_sha256(article.body))


async def confirm_citation(
    session: AsyncSession, link_id: UUID, user_id: UUID, *, now: Optional[datetime] = None
) -> Optional[CitationLinkModel]:
    """El autor confirma una cita: registra quién y cuándo (sin hacer commit).

    No cambia `status`. Devuelve `None` si la cita no existe.
    """
    link = await session.get(CitationLinkModel, link_id)
    if link is None:
        return None
    link.confirmed_by = user_id
    link.confirmed_at = now or datetime.utcnow()
    await session.flush()
    return link
