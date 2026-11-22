"""Cliente de OpenAlex (`/works?search=`). Normaliza sin verificar (T22.2)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.platform.capabilities.literature.models import OPENALEX, Parsed, build_candidate
from app.platform.capabilities.literature.transport import ApiSession, json_then

URL = "https://api.openalex.org/works"


def _abstract(indice: Optional[Dict[str, List[int]]]) -> Optional[str]:
    """OpenAlex entrega el resumen como índice invertido (palabra -> posiciones)."""
    if not isinstance(indice, dict) or not indice:
        return None
    posiciones: Dict[int, str] = {}
    for palabra, lugares in indice.items():
        for lugar in lugares or ():
            posiciones[int(lugar)] = palabra
    return " ".join(posiciones[i] for i in sorted(posiciones)) or None


def parse(datos: Any) -> Parsed:
    resultados = datos["results"]
    if not isinstance(resultados, list):
        raise ValueError("'results' no es una lista")
    candidatos, descartados = [], 0
    for item in resultados:
        if not isinstance(item, dict):
            descartados += 1
            continue
        primaria = item.get("primary_location") or {}
        fuente = primaria.get("source") or {}
        mejor_oa = item.get("best_oa_location") or {}
        abierto = item.get("open_access") or {}
        identificador = str(item.get("id") or "").rsplit("/", 1)[-1]
        candidato = build_candidate(
            OPENALEX,
            title=item.get("title") or item.get("display_name"),
            doi=item.get("doi"),
            source_id=identificador,
            authors=[(a.get("author") or {}).get("display_name") for a in item.get("authorships") or []],
            year=item.get("publication_year"),
            publication_date=item.get("publication_date"),
            journal=fuente.get("display_name"),
            abstract=_abstract(item.get("abstract_inverted_index")),
            url=primaria.get("landing_page_url") or item.get("id"),
            open_access_url=mejor_oa.get("pdf_url") or abierto.get("oa_url"),
        )
        if candidato is None:
            descartados += 1
        else:
            candidatos.append(candidato)
    return Parsed(candidatos, descartados)


async def search(query: str, session: ApiSession, limit: int) -> Parsed:
    params: Dict[str, Any] = {"search": query, "per-page": limit}
    if session.cfg.contact_email:
        params["mailto"] = session.cfg.contact_email
    return await session.request(URL, params=params, parse=json_then(parse))
