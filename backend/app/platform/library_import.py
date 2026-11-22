"""Importar a la biblioteca desde BibTeX o una lista de DOI (SPEC-034 / T22.8 / AC9).

El autor trae referencias que ya conoce. Importar **no** es verificar: cada entrada con DOI
se comprueba con el mismo resolver que la compuerta (por `safe_get`), y solo si el registro
existe y coincide queda `verified` con `doi_resolved`. Lo demás se importa igualmente
—el autor lo pidió— pero **sin verificar**, así que `library.is_citable` lo deja fuera de
`sources` y de Referencias hasta que aporte el DOI (ADR-0011). Falla cerrada: un resolver
caído nunca verifica.

Cada entrada devuelve su propio resultado (`imported` | `duplicate` | `invalid`) para que la
pantalla diga qué pasó con cada una; un lote no se aborta por una entrada mala.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.library_document import (
    CurationStatus, SourceDB, TextStatus, VerificationMethod, normalize_doi,
)
from app.platform import library
from app.platform.capabilities.literature.models import Candidate
from app.platform.capabilities.literature.verification import verify_candidates
from app.platform.egress import QUIEN_LITERATURA
from app.platform.library_upload import UPLOAD_RESOLVER
from app.platform.publication_gate import reference_resolver as rr

logger = logging.getLogger(__name__)

MAX_ENTRIES = 100

IMPORTED = "imported"
DUPLICATE = "duplicate"
INVALID = "invalid"

_DOI_RE = re.compile(r"10\.\d{4,9}/\S+", re.IGNORECASE)


# ── BibTeX ───────────────────────────────────────────────────────────────────

def _read_braced(text: str, i: int) -> tuple[str, int]:
    """Lee un valor `{...}` (con llaves anidadas) desde `text[i] == '{'`."""
    depth, j = 0, i
    while j < len(text):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1:j], j + 1
        j += 1
    return text[i + 1:], len(text)


def _clean(value: str) -> str:
    value = re.sub(r"\\[`'^\"~=.]\{?(\w)\}?", r"\1", value)  # acentos LaTeX → letra base
    value = value.replace("\\&", "&")
    value = value.replace("{", "").replace("}", "")
    return " ".join(value.split())


def parse_bibtex(text: str) -> List[Dict[str, str]]:
    """Entradas de un BibTeX como `{campo: valor}` (campos en minúsculas, `_type` y `_key`).

    Parser deliberadamente pequeño: `@tipo{clave, campo = {..} | ".." | número, ...}`. Ignora
    `@comment`, `@string` y `@preamble`. No expande macros ni `#`.
    """
    entradas: List[Dict[str, str]] = []
    pos = 0
    cabecera = re.compile(r"@(\w+)\s*\{", re.ASCII)
    while True:
        m = cabecera.search(text, pos)
        if not m:
            break
        tipo = m.group(1).lower()
        cuerpo, pos = _read_braced(text, m.end() - 1)
        if tipo in {"comment", "string", "preamble"}:
            continue
        clave, _, resto = cuerpo.partition(",")
        entrada: Dict[str, str] = {"_type": tipo, "_key": clave.strip()}
        j = 0
        campo = re.compile(r"\s*,?\s*(\w+)\s*=\s*")
        while True:
            c = campo.match(resto, j)
            if not c:
                break
            nombre, j = c.group(1).lower(), c.end()
            if j >= len(resto):
                break
            if resto[j] == "{":
                valor, j = _read_braced(resto, j)
            elif resto[j] == '"':
                fin = resto.find('"', j + 1)
                fin = len(resto) if fin == -1 else fin
                valor, j = resto[j + 1:fin], fin + 1
            else:
                fin = resto.find(",", j)
                fin = len(resto) if fin == -1 else fin
                valor, j = resto[j:fin].strip(), fin
            entrada.setdefault(nombre, _clean(valor))
        entradas.append(entrada)
    return entradas


def _bib_authors(raw: str) -> List[str]:
    """`Apellido, Nombre and Otro, Nombre` → ['Nombre Apellido', ...]."""
    salida = []
    for a in re.split(r"\s+and\s+", raw or "", flags=re.IGNORECASE):
        a = a.strip()
        if "," in a:
            ap, _, nom = a.partition(",")
            a = f"{nom.strip()} {ap.strip()}".strip()
        if a:
            salida.append(a)
    return salida


def parse_dois(text: str) -> List[str]:
    """DOI de una lista libre (uno por línea, coma o espacio; admite `https://doi.org/`). Sin repetidos."""
    vistos: Dict[str, None] = {}
    for crudo in re.split(r"[\s,;]+", text or ""):
        doi = normalize_doi(crudo)
        if doi and _DOI_RE.fullmatch(doi):
            vistos.setdefault(doi, None)
    return list(vistos)


# ── Importación ──────────────────────────────────────────────────────────────

def _year(value: Any) -> Optional[int]:
    m = re.search(r"\d{4}", str(value or ""))
    return int(m.group()) if m else None


def _result(ref: str, estado: str, detail: str = "", doc: Any = None, verified: bool = False) -> Dict[str, Any]:
    return {"ref": ref, "status": estado, "detail": detail, "verified": verified,
            "document_id": str(doc.id) if doc is not None else None}


async def _add(session, project_id, added_by, *, verified_at: Optional[datetime] = None, **campos):
    """Alta como `accepted` (lo pidió el autor); verificada solo si `verified_at` lo acredita."""
    if verified_at is not None:
        campos.update(verified=True, verification_method=VerificationMethod.DOI_RESOLVED.value,
                      verified_at=verified_at)
    return await library.add_document(
        session, project_id, added_by=added_by, source_db=SourceDB.MANUAL.value,
        text_status=TextStatus.ABSTRACT_ONLY.value,
        curation_status=CurationStatus.ACCEPTED.value, **campos,
    )


async def import_bibtex(
    session: AsyncSession, project_id: UUID, text: str, *, added_by: UUID | None = None,
    fetch: Any = None,
) -> List[Dict[str, Any]]:
    resultados: List[Dict[str, Any]] = []
    for e in parse_bibtex(text)[:MAX_ENTRIES]:
        ref = e.get("_key") or e.get("title", "")[:40] or "(sin clave)"
        titulo = e.get("title", "").strip()
        if not titulo:
            resultados.append(_result(ref, INVALID, "la entrada no tiene título"))
            continue
        doi = normalize_doi(e.get("doi") or "")
        autores = _bib_authors(e.get("author", ""))
        campos: Dict[str, Any] = dict(
            title=titulo, authors=autores, year=_year(e.get("year") or e.get("date")),
            journal=e.get("journal") or e.get("journaltitle") or e.get("booktitle") or None,
            url=e.get("url") or None,
        )
        detalle, verified_at = "sin DOI: queda sin verificar hasta que aportes uno", None
        if doi:
            cand = Candidate(title=titulo, source_db=SourceDB.MANUAL.value, doi=doi,
                             authors=tuple(autores), year=campos["year"], journal=campos["journal"])
            try:
                res = await verify_candidates([cand], datetime.utcnow(), resolver=UPLOAD_RESOLVER, fetch=fetch)
            except Exception as error:  # falla cerrada
                logger.exception("library_import: error verificando %s", doi)
                res = None
                detalle = f"no se pudo verificar ({type(error).__name__}); queda sin verificar"
                campos["doi"] = doi
            if res is not None and res.verified:
                v = res.verified[0]
                campos.update(doi=v.doi, year=v.candidate.year, journal=v.candidate.journal,
                              authors=list(v.candidate.authors) or autores)
                verified_at, detalle = v.verified_at, f"verificado ({v.provider})"
            elif res is not None:
                d = res.discarded[0] if res.discarded else None
                detalle = f"DOI sin verificar: {d.detail if d else 'sin resultado'}"
                if d is not None and d.not_verified:
                    campos["doi"] = doi  # el resolver no respondió: se conserva para reintentar
        try:
            doc = await _add(session, project_id, added_by, verified_at=verified_at, **campos)
        except library.DuplicateDocumentError:
            resultados.append(_result(ref, DUPLICATE, "ese DOI ya está en la biblioteca del proyecto"))
            continue
        resultados.append(_result(ref, IMPORTED, detalle, doc, verified_at is not None))
    return resultados


async def import_dois(
    session: AsyncSession, project_id: UUID, text: str, *, added_by: UUID | None = None,
    fetch: Any = None,
) -> List[Dict[str, Any]]:
    resultados: List[Dict[str, Any]] = []
    sess = rr.open_session(UPLOAD_RESOLVER, fetch=fetch or rr.fetch_for(QUIEN_LITERATURA),
                           metrics=rr.NO_METRICS, user_agent="AlejandrIA-LibraryImport/1.0")
    for doi in parse_dois(text)[:MAX_ENTRIES]:
        if await library.find_by_doi(session, project_id, doi) is not None:
            resultados.append(_result(doi, DUPLICATE, "ya está en la biblioteca del proyecto"))
            continue
        try:
            rec = await rr.lookup_doi(sess, doi)
        except rr.Unavailable as error:
            resultados.append(_result(doi, INVALID, f"el resolver no respondió ({error}); reintenta"))
            continue
        except Exception as error:  # falla cerrada
            logger.exception("library_import: error resolviendo %s", doi)
            resultados.append(_result(doi, INVALID, f"error resolviendo el DOI ({type(error).__name__})"))
            continue
        if rec is None:
            resultados.append(_result(doi, INVALID, "el DOI no existe en Crossref ni en OpenAlex"))
            continue
        try:
            doc = await _add(session, project_id, added_by, verified_at=datetime.utcnow(),
                             doi=normalize_doi(rec.doi) or doi, title=rec.title or doi,
                             authors=list(rec.authors), year=rec.year, journal=rec.journal or None)
        except library.DuplicateDocumentError:
            resultados.append(_result(doi, DUPLICATE, "ya está en la biblioteca del proyecto"))
            continue
        resultados.append(_result(doi, IMPORTED, f"verificado ({rec.provider})", doc, True))
    return resultados
