"""Cliente de PubMed (NCBI E-utilities): `esearch` para los PMID y `efetch` para el detalle.

Dos peticiones por consulta, ambas por la sesión con reintentos. `esearch` solo lleva la
cadena de búsqueda; `efetch`, los PMID que devolvió. NCBI pide identificar al cliente con
`tool` y `email`; el correo es el de contacto de la plataforma, si está configurado.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional

from app.platform.capabilities.literature.models import PUBMED, Parsed, build_candidate
from app.platform.capabilities.literature.transport import ApiSession, json_then, xml_then

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
HERRAMIENTA = "AlejandrIA-LiteratureDiscovery"
_MESES = {m: f"{i:02d}" for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse_ids(datos: Any) -> list:
    ids = datos["esearchresult"]["idlist"]
    if not isinstance(ids, list):
        raise ValueError("'idlist' no es una lista")
    return [str(i) for i in ids]


def _texto(nodo: Optional[ET.Element]) -> str:
    return " ".join("".join(nodo.itertext()).split()) if nodo is not None else ""


def _fecha(articulo: ET.Element) -> Optional[str]:
    pub = articulo.find("Journal/JournalIssue/PubDate")
    if pub is None:
        return None
    anio = _texto(pub.find("Year"))
    if not anio:
        # `MedlineDate` es texto libre («2019 Jan-Feb»): solo se aprovecha el año.
        libre = _texto(pub.find("MedlineDate"))[:4]
        return libre if libre.isdigit() else None
    mes = _MESES.get(_texto(pub.find("Month"))[:3].lower()) or (
        _texto(pub.find("Month")).zfill(2) if _texto(pub.find("Month")).isdigit() else None)
    dia = _texto(pub.find("Day"))
    if mes and dia.isdigit():
        return f"{anio}-{mes}-{dia.zfill(2)}"
    return f"{anio}-{mes}" if mes else anio


def parse_articles(raiz: ET.Element) -> Parsed:
    if raiz.tag != "PubmedArticleSet":
        raise ValueError(f"se esperaba <PubmedArticleSet>, no <{raiz.tag}>")
    candidatos, descartados = [], 0
    for registro in raiz.findall("PubmedArticle"):
        cita = registro.find("MedlineCitation")
        articulo = cita.find("Article") if cita is not None else None
        if cita is None or articulo is None:
            descartados += 1
            continue
        pmid = _texto(cita.find("PMID"))
        doi = next(
            (_texto(i) for i in registro.findall("PubmedData/ArticleIdList/ArticleId")
             if i.get("IdType") == "doi"), None)
        autores = []
        for a in articulo.findall("AuthorList/Author"):
            apellido, nombre = _texto(a.find("LastName")), _texto(a.find("ForeName"))
            autores.append(f"{nombre} {apellido}".strip() or _texto(a.find("CollectiveName")))
        resumen = " ".join(_texto(t) for t in articulo.findall("Abstract/AbstractText"))
        fecha = _fecha(articulo)
        candidato = build_candidate(
            PUBMED,
            title=_texto(articulo.find("ArticleTitle")),
            doi=doi,
            source_id=pmid,
            authors=autores,
            year=fecha[:4] if fecha else None,
            publication_date=fecha,
            journal=_texto(articulo.find("Journal/Title")),
            abstract=resumen,
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
        )
        if candidato is None:
            descartados += 1
        else:
            candidatos.append(candidato)
    return Parsed(candidatos, descartados)


def _identidad(session: ApiSession) -> Dict[str, str]:
    extra = {"tool": HERRAMIENTA}
    if session.cfg.contact_email:
        extra["email"] = session.cfg.contact_email
    if session.cfg.ncbi_key:
        extra["api_key"] = session.cfg.ncbi_key
    return extra


async def search(query: str, session: ApiSession, limit: int) -> Parsed:
    busqueda = {"db": "pubmed", "term": query, "retmax": limit, "retmode": "json",
                **_identidad(session)}
    ids = await session.request(ESEARCH, params=busqueda, parse=json_then(parse_ids))
    if not ids:
        return Parsed([], 0)
    detalle = {"db": "pubmed", "id": ",".join(ids), "retmode": "xml", **_identidad(session)}
    return await session.request(EFETCH, params=detalle, parse=xml_then(parse_articles))
