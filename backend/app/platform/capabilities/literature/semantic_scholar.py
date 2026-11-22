"""Cliente de Semantic Scholar (Graph API, `/paper/search`).

Solo se consulta con clave de API en el entorno (`SEMANTIC_SCHOLAR_API_KEY`); la clave
viaja en la cabecera `x-api-key`, nunca en la URL. La comprobación de que existe vive en
`discovery.py`, que omite la base con un aviso explícito si falta.
"""
from __future__ import annotations

from typing import Any, Dict

from app.platform.capabilities.literature.models import SEMANTIC_SCHOLAR, Parsed, build_candidate
from app.platform.capabilities.literature.transport import ApiSession, json_then

URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_CAMPOS = "title,authors,year,publicationDate,abstract,externalIds,url,venue,openAccessPdf"


def parse(datos: Any) -> Parsed:
    items = datos["data"]
    if not isinstance(items, list):
        raise ValueError("'data' no es una lista")
    candidatos, descartados = [], 0
    for item in items:
        if not isinstance(item, dict):
            descartados += 1
            continue
        externos = item.get("externalIds") or {}
        candidato = build_candidate(
            SEMANTIC_SCHOLAR,
            title=item.get("title"),
            doi=externos.get("DOI"),
            source_id=item.get("paperId"),
            authors=[a.get("name") for a in item.get("authors") or []],
            year=item.get("year"),
            publication_date=item.get("publicationDate"),
            journal=item.get("venue"),
            abstract=item.get("abstract"),
            url=item.get("url"),
            open_access_url=(item.get("openAccessPdf") or {}).get("url"),
        )
        if candidato is None:
            descartados += 1
        else:
            candidatos.append(candidato)
    return Parsed(candidatos, descartados)


async def search(query: str, session: ApiSession, limit: int) -> Parsed:
    params: Dict[str, Any] = {"query": query, "limit": limit, "fields": _CAMPOS}
    cabeceras = {"x-api-key": session.cfg.semantic_scholar_key}
    return await session.request(URL, params=params, headers=cabeceras, parse=json_then(parse))
