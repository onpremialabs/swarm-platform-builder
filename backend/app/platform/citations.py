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
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
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


# ── Citas por identificador de fragmento (T23.1) ───────────────────────────
# Contrato que escribe el Redactor y consumen T23.2 (arriba) y T23.3.
_CONTRATO_T23_1 = """Contrato de citas por identificador de fragmento (SPEC-035 / T23.1).

Este módulo es **el único sitio** que define cómo se nombra un fragmento y cómo se
lee una cita del texto. T23.2 (persistencia) y T23.3 (criterio de compuerta) lo
consumen; no deben reinterpretar el formato.

Contrato
--------
* **Identificador de fragmento** ('fragment_id'): ''"<doc_id>#<chunk_index>"'', p. ej.
  ''"4f1c...#7"''. Es estable (no depende del orden de recuperación) y se resuelve
  contra el índice. Si el índice no aportó ''chunk_index'' se usa el ''chunk_id'' del punto.
* **Marcador de cita** ('cite_id'): ''F<n>'' (''F1'', ''F2''...). Es un alias corto que
  el Redactor ve en el prompt y escribe en el texto como ''[F3]'' (o ''[F1, F3]'').
  Un alias identifica un fragmento durante todo el artículo: entre vueltas del bucle
  del revisor se conserva (''assign_cite_ids(..., previous=...)'').
* **Mapa** ('citation_map', ''AgentState["citation_map"]''): ''{cite_id: entrada}'' con
  ''entrada = {fragment_id, doc_id, chunk_index, filename, page, extract, hash}''.
  ''hash'' es el SHA-256 del texto **completo** del fragmento; ''extract'' es su inicio
  (''EXTRACT_CHARS''); ''page'' es ''None'' mientras la indexación no la guarde
  (degrada a «sección desconocida», SPEC-035 §5).
* **Citas** ('citations', ''AgentState["citations"]''): una por cada par
  (afirmación, marcador) del borrador: ''{cite_id, claim, fragment_id|None, ...entrada}''.
  ''claim'' es la frase que acompaña a la cita. Es lo que T23.2 versiona con el hash
  del texto evaluado (''text_hash'').
* **Sin soporte**: un marcador ausente del mapa (alias inventado) o un borrador sin
  ningún marcador no produce entrada en el mapa: va a ''unresolved'' y T23.3 lo marca
  ''not_verified'' (falla cerrada, ADR-0011). Aquí no se bloquea nada.

Todo es determinista y sin E/S.
"""

EXTRACT_CHARS = 280

# `[F3]`, `[F1, F3]`, `[F1; F2]`
_BRACKET = re.compile(r"\[\s*(F\d+(?:\s*[,;]\s*F\d+)*)\s*\]")
_CITE = re.compile(r"F\d+")
# Cita autor-año entre paréntesis: «(HarnessDev, 2024)», «(Code as Agent Harness et al., 2024)»,
# «(Smith & Lee 2020; Ruiz, 2021)». No es una cita válida (T23.9 / AC10): el contrato es `[F#]`.
_AUTOR_ANIO = re.compile(r"\(\s*[A-ZÁÉÍÓÚÜÑ][^()\[\]]*?(?:,\s*|\s)(?:19|20)\d{2}[a-z]?\b[^()\[\]]*\)")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n{2,}|\n(?=#|\s*[-*]\s)")


def text_hash(text: str) -> str:
    """SHA-256 hexadecimal del texto (usado para fragmentos y para el borrador evaluado)."""
    return excerpt_sha256(text)


def fragment_id(result: Dict[str, Any]) -> Optional[str]:
    """Identificador estable de un resultado del RAG, o None si no hay de qué derivarlo."""
    doc_id = str(result.get("doc_id") or "").strip()
    if not doc_id:
        return None
    idx = result.get("chunk_index")
    if idx is None:
        idx = result.get("chunk_id")
    if idx is None:
        return None
    return f"{doc_id}#{idx}"


def assign_cite_ids(
    results: Iterable[Dict[str, Any]],
    previous: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Mapa `cite_id → entrada` para los fragmentos recuperados.

    Los alias de `previous` se conservan para los mismos fragmentos y los nuevos continúan
    la numeración, de modo que un borrador anterior sigue siendo legible.
    """
    mapa: Dict[str, Dict[str, Any]] = {}
    por_fragmento: Dict[str, str] = {}
    siguiente = 1
    for cid, entrada in (previous or {}).items():
        mapa[cid] = dict(entrada)
        por_fragmento[entrada.get("fragment_id")] = cid
        m = _CITE.fullmatch(cid)
        if m:
            siguiente = max(siguiente, int(cid[1:]) + 1)
    for r in results:
        fid = fragment_id(r)
        texto = (r.get("text") or "").strip()
        if not fid or not texto or fid in por_fragmento:
            continue
        cid = f"F{siguiente}"
        siguiente += 1
        por_fragmento[fid] = cid
        mapa[cid] = {
            "fragment_id": fid,
            "doc_id": str(r.get("doc_id")),
            "chunk_index": r.get("chunk_index"),
            "filename": r.get("filename") or "",
            "page": r.get("page"),
            "extract": texto[:EXTRACT_CHARS],
            "hash": text_hash(texto),
        }
    return mapa


def render_fragments(results: Iterable[Dict[str, Any]], mapa: Dict[str, Dict[str, Any]], language: str = "es") -> str:
    """Bloque de prompt: cada fragmento citable con su marcador y la regla de cita."""
    por_fragmento = {e["fragment_id"]: cid for cid, e in mapa.items()}
    bloques = []
    for r in results:
        cid = por_fragmento.get(fragment_id(r) or "")
        texto = (r.get("text") or "").strip()
        if cid and texto:
            origen = f" {r['origin']}" if r.get("origin") else ""
            bloques.append(f"[{cid}] ({r.get('filename') or r.get('doc_title') or ''}){origen}\n{texto}")
    if not bloques:
        return ""
    if language == "es":
        regla = ("Cita ÚNICAMENTE con el marcador del fragmento que respalda la frase, así: [F1] o [F1, F2]. "
                 "No inventes marcadores ni cites nada que no esté en esta lista. "
                 "NO uses citas autor-año como (Autor, 2024): no son válidas.")
        cab = "### Fragmentos citables"
    else:
        regla = ("Cite ONLY with the marker of the fragment that supports the sentence, like [F1] or [F1, F2]. "
                 "Do not invent markers or cite anything not in this list. "
                 "Do NOT use author-year citations like (Author, 2024): they are not valid.")
        cab = "### Citable fragments"
    return f"{cab}\n{regla}\n\n" + "\n\n".join(bloques)


def extract_citations(draft: str, mapa: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Lee las citas del borrador contra el mapa.

    Devuelve ``{"citations": [...], "unresolved": [cite_id...], "map": {...solo los usados},
    "text_hash": str, "author_year": [...], "valid_citations": int}``.

    Una cita autor-año («(Título, 2024)») **no es una cita válida** (T23.9 / AC10): se trata como
    una cita sin fragmento —entra en ``citations`` y ``unresolved`` con su texto literal como
    clave y ``fragment_id`` ``None``, así que la compuerta la deja ``not_verified``—. Solo cuentan
    como válidas (``valid_citations``) las que apuntan a un fragmento del mapa.
    """
    citas: List[Dict[str, Any]] = []
    sin_resolver: List[str] = []
    autor_anio: List[str] = []
    usados: Dict[str, Dict[str, Any]] = {}
    texto = draft or ""
    for frase in _split_sentences(texto):
        for m in _BRACKET.finditer(frase):
            claim = re.sub(r"\s*" + _BRACKET.pattern, "", frase).strip()
            for cid in _CITE.findall(m.group(1)):
                entrada = mapa.get(cid)
                if entrada is None:
                    if cid not in sin_resolver:
                        sin_resolver.append(cid)
                    citas.append({"cite_id": cid, "claim": claim, "fragment_id": None})
                    continue
                usados[cid] = entrada
                citas.append({"cite_id": cid, "claim": claim, **entrada})
        for m in _AUTOR_ANIO.finditer(frase):
            cruda = re.sub(r"\s+", " ", m.group(0))[:120]
            claim = re.sub(r"\s*" + _AUTOR_ANIO.pattern, "", re.sub(r"\s*" + _BRACKET.pattern, "", frase)).strip()
            if cruda not in autor_anio:
                autor_anio.append(cruda)
            if cruda not in sin_resolver:
                sin_resolver.append(cruda)
            citas.append({"cite_id": cruda, "claim": claim, "fragment_id": None, "format": "author_year"})
    validas = sum(1 for c in citas if c.get("fragment_id"))
    return {"citations": citas, "unresolved": sin_resolver, "map": usados,
            "text_hash": text_hash(texto), "author_year": autor_anio, "valid_citations": validas}


def _split_sentences(texto: str) -> List[str]:
    return [p for p in _SENTENCE_END.split(texto) if p and p.strip()]


def to_citation_inputs(citations: Iterable[Dict[str, Any]]) -> List[CitationInput]:
    """Puente hacia `save_citation_map`: las citas del Redactor -> `CitationInput`.

    Una cita sin fragmento (`fragment_id` None) llega sin doc/extracto y `save_citation_map`
    la deja `not_verified` (falla cerrada). `citation_key` es el `cite_id` (`F#`); el mapa se
    versiona con el hash del texto que se pase a `save_citation_map`.
    """
    return [
        CitationInput(
            citation_key=c["cite_id"], claim=c.get("claim") or "",
            doc_id=c.get("doc_id"), page=c.get("page"), excerpt=c.get("extract") or "",
        )
        for c in citations
    ]


# ── Recordatorio de formato (T23.9 / AC10) ──────────────────────────────────

_RECORDATORIO = {
    "es": ("\n\nRECORDATORIO OBLIGATORIO DEL FORMATO DE CITA: tu borrador anterior no citó ningún "
           "fragmento con su marcador. Cada afirmación sustantiva se cita con el marcador del "
           "fragmento que la respalda, entre corchetes, p. ej. «La HbA1c bajó un 1,1 % [F1].» o "
           "«... [F1, F3].». NO uses citas autor-año como (Autor, 2024) ni el título de una obra como "
           "autor: no son válidas. Reescribe el borrador completo citando con [F#]."),
    "en": ("\n\nMANDATORY CITATION FORMAT REMINDER: your previous draft did not cite any fragment with "
           "its marker. Every substantive claim is cited with the marker of the fragment that supports "
           "it, in square brackets, e.g. \"HbA1c fell by 1.1% [F1].\" or \"... [F1, F3].\". Do NOT use "
           "author-year citations like (Author, 2024) or a work's title as author: they are not valid. "
           "Rewrite the full draft citing with [F#]."),
}


def format_reminder(language: str = "es") -> str:
    """Recordatorio explícito del formato `[F#]` para el único reintento del Redactor."""
    return _RECORDATORIO["es" if (language or "es").lower() == "es" else "en"]
