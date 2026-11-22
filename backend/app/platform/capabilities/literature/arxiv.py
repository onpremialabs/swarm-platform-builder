"""Cliente de arXiv (API Atom, `export.arxiv.org/api/query`).

Todo arXiv es acceso abierto: el enlace `pdf` del registro es `open_access_url`. El DOI
es el del artículo publicado si el autor lo declaró; si no, el DOI propio de arXiv
(`10.48550/arxiv.<id>`), que registra DataCite y es determinista.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Dict

from app.platform.capabilities.literature.models import ARXIV, Parsed, build_candidate
from app.platform.capabilities.literature.transport import ApiSession, xml_then

URL = "https://export.arxiv.org/api/query"
_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"
_VERSION = re.compile(r"v\d+$")


def _texto(nodo: ET.Element, etiqueta: str) -> str:
    hijo = nodo.find(etiqueta)
    return " ".join("".join(hijo.itertext()).split()) if hijo is not None else ""


def parse(raiz: ET.Element) -> Parsed:
    if raiz.tag != f"{_ATOM}feed":
        raise ValueError(f"se esperaba un <feed> Atom, no <{raiz.tag}>")
    candidatos, descartados = [], 0
    for entrada in raiz.findall(f"{_ATOM}entry"):
        url = _texto(entrada, f"{_ATOM}id")
        identificador = _VERSION.sub("", url.split("/abs/", 1)[-1]) if "/abs/" in url else ""
        doi = _texto(entrada, f"{_ARXIV}doi") or (
            f"10.48550/arxiv.{identificador}" if identificador else None
        )
        pdf = next(
            (l.get("href") for l in entrada.findall(f"{_ATOM}link") if l.get("title") == "pdf"), None
        )
        fecha = _texto(entrada, f"{_ATOM}published")[:10] or None
        candidato = build_candidate(
            ARXIV,
            title=_texto(entrada, f"{_ATOM}title"),
            doi=doi,
            source_id=identificador,
            authors=[_texto(a, f"{_ATOM}name") for a in entrada.findall(f"{_ATOM}author")],
            year=fecha[:4] if fecha else None,
            publication_date=fecha,
            journal=_texto(entrada, f"{_ARXIV}journal_ref") or None,
            abstract=_texto(entrada, f"{_ATOM}summary"),
            url=url or None,
            open_access_url=pdf,
        )
        if candidato is None:
            descartados += 1
        else:
            candidatos.append(candidato)
    return Parsed(candidatos, descartados)


async def search(query: str, session: ApiSession, limit: int) -> Parsed:
    params: Dict[str, Any] = {"search_query": f"all:{query}", "max_results": limit}
    return await session.request(URL, params=params, parse=xml_then(parse))
