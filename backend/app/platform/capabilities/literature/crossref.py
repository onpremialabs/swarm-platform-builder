"""Cliente de Crossref (`/works?query=`). Normaliza sin verificar (T22.2).

Crossref no informa de acceso abierto de forma fiable en la búsqueda, así que
`open_access_url` queda vacío: es mejor no decirlo que decirlo mal (SPEC-034/AC11).
"""
from __future__ import annotations

import html
import re
from typing import Any, Dict, List, Optional

from app.platform.capabilities.literature.models import CROSSREF, Parsed, build_candidate
from app.platform.capabilities.literature.transport import ApiSession, json_then

URL = "https://api.crossref.org/works"
_CAMPOS = "DOI,title,author,issued,abstract,URL,container-title"
_ETIQUETAS = re.compile(r"<[^>]+>")


def _fecha(item: dict) -> Optional[str]:
    partes = ((item.get("issued") or {}).get("date-parts") or [[]])[0] or []
    if not partes or partes[0] is None:
        return None
    return "-".join([f"{int(partes[0]):04d}"] + [f"{int(p):02d}" for p in partes[1:3] if p is not None])


def _autores(item: dict) -> List[str]:
    nombres = []
    for a in item.get("author") or []:
        familia, dado = a.get("family"), a.get("given")
        nombres.append(f"{dado} {familia}".strip() if familia and dado else (familia or a.get("name") or ""))
    return nombres


def _resumen(texto: Optional[str]) -> Optional[str]:
    """El resumen de Crossref viene en JATS (`<jats:p>...`)."""
    if not texto:
        return None
    return " ".join(html.unescape(_ETIQUETAS.sub(" ", texto)).split()) or None


def parse(datos: Any) -> Parsed:
    items = datos["message"]["items"]
    if not isinstance(items, list):
        raise ValueError("'message.items' no es una lista")
    candidatos, descartados = [], 0
    for item in items:
        if not isinstance(item, dict):
            descartados += 1
            continue
        fecha = _fecha(item)
        candidato = build_candidate(
            CROSSREF,
            title=(item.get("title") or [""])[0],
            doi=item.get("DOI"),
            source_id=item.get("DOI"),
            authors=_autores(item),
            year=int(fecha[:4]) if fecha else None,
            publication_date=fecha,
            journal=(item.get("container-title") or [""])[0],
            abstract=_resumen(item.get("abstract")),
            url=item.get("URL"),
        )
        if candidato is None:
            descartados += 1
        else:
            candidatos.append(candidato)
    return Parsed(candidatos, descartados)


async def search(query: str, session: ApiSession, limit: int) -> Parsed:
    params: Dict[str, Any] = {"query": query, "rows": limit, "select": _CAMPOS}
    if session.cfg.contact_email:
        params["mailto"] = session.cfg.contact_email
    return await session.request(URL, params=params, parse=json_then(parse))
