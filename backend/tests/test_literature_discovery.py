"""SPEC-034 / T22.1 — capacidad `literature` (AC1, AC10). Sin red real.

Los clientes se prueban con respuestas **representativas y reducidas** de cada API
(forma documentada, datos inventados) inyectadas en lugar de `safe_get`. Lo que se
vigila: la normalización de cada base, que **nada sale verificado**, los reintentos con
espera exponencial, que el fallo de una base no tumba a las demás y que se ve, que el
host solo se abre a esta capacidad y que nadie abre un cliente HTTP propio.
"""
import ast
import json
import os
import shutil
import socket
import sys
from pathlib import Path

import httpx
import pytest
import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("SECRET_KEY", "ci-secret-not-for-prod")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_literature.db")

from app.platform import egress  # noqa: E402
from app.platform.capabilities import registry  # noqa: E402
from app.platform.capabilities.binding import bind  # noqa: E402
from app.platform.capabilities.literature import (  # noqa: E402
    DEFAULT_SOURCES, KNOWN_SOURCES, Candidate, LiteratureConfig, LiteratureQueryError,
    UnknownSourceError, search_literature,
)
from app.platform.capabilities.literature import arxiv, crossref, openalex, pubmed, semantic_scholar  # noqa: E402
from app.platform.capabilities.literature.models import build_candidate, normalize_doi  # noqa: E402
from app.platform.capabilities.literature.research import ResearchConfigError, parse_research  # noqa: E402
from app.platform.capabilities.literature.transport import (  # noqa: E402
    xml_root,
)
from app.platform.projects import loader  # noqa: E402
from app.platform.projects.loader import TemplateError  # noqa: E402

LIT_DIR = ROOT_DIR / "app" / "platform" / "capabilities" / "literature"

# ── Respuestas representativas ──────────────────────────────────────────────

OPENALEX_JSON = {"results": [
    {
        "id": "https://openalex.org/W2741809807",
        "doi": "https://doi.org/10.1038/S41586-020-2649-2",
        "title": "Array programming with NumPy",
        "publication_year": 2020, "publication_date": "2020-09-16",
        "authorships": [{"author": {"display_name": "Charles R. Harris"}},
                        {"author": {"display_name": "K. Jarrod Millman"}}],
        "primary_location": {"landing_page_url": "https://doi.org/10.1038/s41586-020-2649-2",
                             "source": {"display_name": "Nature"}},
        "best_oa_location": {"pdf_url": "https://europepmc.org/articles/pmc7759461?pdf=render"},
        "open_access": {"oa_url": "https://europepmc.org/articles/pmc7759461"},
        "abstract_inverted_index": {"Array": [0], "programming": [1], "is": [2], "powerful": [3]},
    },
    {"id": "https://openalex.org/W1", "doi": None, "title": "Sin DOI pero con id",
     "publication_year": 2019, "authorships": [], "primary_location": None},
    {"id": "https://openalex.org/W2", "doi": "https://doi.org/10.1/x", "title": None},
    {"id": None, "doi": None, "title": "Sin ninguna identificación"},
]}

CROSSREF_JSON = {"status": "ok", "message": {"items": [
    {
        "DOI": "10.1126/SCIENCE.1259855", "URL": "http://dx.doi.org/10.1126/science.1259855",
        "title": ["The   Genome of  a Mammal"], "container-title": ["Science"],
        "author": [{"given": "Ada", "family": "Lovelace"}, {"name": "The Consortium"}],
        "issued": {"date-parts": [[2015, 3, 5]]},
        "abstract": "<jats:p>Un &amp; resumen <jats:italic>con</jats:italic> etiquetas.</jats:p>",
    },
    {"DOI": "10.1/solo-anio", "title": ["Solo año"], "issued": {"date-parts": [[2001]]}},
    {"DOI": "10.1/sin-titulo", "title": []},
]}}

S2_JSON = {"total": 2, "data": [
    {"paperId": "649def34f8be52c8b66281af98ae884c09aef38b", "title": "Attention Is All You Need",
     "year": 2017, "publicationDate": "2017-06-12", "venue": "NIPS", "abstract": "Un resumen.",
     "url": "https://www.semanticscholar.org/paper/649def34",
     "authors": [{"name": "Ashish Vaswani"}], "externalIds": {"DOI": "10.5555/3295222.3295349", "ArXiv": "1706.03762"},
     "openAccessPdf": {"url": "https://arxiv.org/pdf/1706.03762.pdf"}},
    {"paperId": None, "title": "Sin id ni DOI", "externalIds": {}},
]}

ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <published>2017-06-12T17:57:34Z</published>
    <title>Attention Is All
      You Need</title>
    <summary>  The dominant sequence transduction models.  </summary>
    <author><name>Ashish Vaswani</name></author><author><name>Noam Shazeer</name></author>
    <link href="http://arxiv.org/abs/1706.03762v7" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/1706.03762v7" rel="related" type="application/pdf"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/hep-th/9901001v1</id><published>1999-01-01T00:00:00Z</published>
    <title>Con DOI de revista</title><summary>x</summary><author><name>A. B</name></author>
    <arxiv:doi>10.1000/J.Real.1</arxiv:doi><arxiv:journal_ref>Phys. Rev. D 1</arxiv:journal_ref>
  </entry>
  <entry><id>http://arxiv.org/api/errors#x</id><title>Error</title><summary>algo</summary></entry>
</feed>"""

PUBMED_SEARCH_JSON = {"esearchresult": {"count": "1", "idlist": ["31452104"]}}
PUBMED_FETCH_XML = """<?xml version="1.0" ?>
<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2023//EN" "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_230101.dtd">
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">31452104</PMID>
      <Article>
        <Journal><Title>The Lancet</Title>
          <JournalIssue><PubDate><Year>2019</Year><Month>Aug</Month><Day>7</Day></PubDate></JournalIssue></Journal>
        <ArticleTitle>Efecto de <i>algo</i> en algo.</ArticleTitle>
        <Abstract><AbstractText Label="A">Primera parte.</AbstractText><AbstractText>Segunda.</AbstractText></Abstract>
        <AuthorList><Author><LastName>Garcia</LastName><ForeName>Ana</ForeName></Author>
          <Author><CollectiveName>Grupo X</CollectiveName></Author></AuthorList>
      </Article>
    </MedlineCitation>
    <PubmedData><ArticleIdList><ArticleId IdType="pubmed">31452104</ArticleId>
      <ArticleId IdType="doi">10.1016/S0140-6736(19)31234-5</ArticleId></ArticleIdList></PubmedData>
  </PubmedArticle>
  <PubmedArticle><MedlineCitation><PMID>999</PMID><Article><ArticleTitle></ArticleTitle></Article></MedlineCitation></PubmedArticle>
</PubmedArticleSet>"""


class Resp:
    def __init__(self, status=200, *, json_body=None, text=None, headers=None):
        self.status_code = status
        self._json, self.text, self.headers = json_body, text, headers or {}
        if text is None and json_body is not None:
            self.text = json.dumps(json_body)

    def json(self):
        if self._json is None:
            return json.loads(self.text)
        return self._json


class FakeApi:
    """Sustituye `safe_get`: reparte respuestas por host y anota lo que se pidió."""

    def __init__(self, por_host):
        self.por_host = por_host  # host -> Resp | lista de Resp/Exception | callable
        self.llamadas = []

    async def __call__(self, url, **kw):
        host = httpx.URL(url).host
        self.llamadas.append({"url": url, "host": host, **kw})
        respuesta = self.por_host[host]
        if isinstance(respuesta, list):
            respuesta = respuesta.pop(0) if len(respuesta) > 1 else respuesta[0]
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


class Pausas:
    def __init__(self):
        self.valores = []

    async def __call__(self, segundos):
        self.valores.append(segundos)


CFG = LiteratureConfig(retries=2, backoff_s=1.0, max_backoff_s=30.0, max_results=5,
                       semantic_scholar_key="clave-de-prueba")


def _bien():
    return {
        "api.openalex.org": Resp(json_body=OPENALEX_JSON),
        "api.crossref.org": Resp(json_body=CROSSREF_JSON),
        "api.semanticscholar.org": Resp(json_body=S2_JSON),
        "export.arxiv.org": Resp(text=ARXIV_XML),
        "eutils.ncbi.nlm.nih.gov": [Resp(json_body=PUBMED_SEARCH_JSON), Resp(text=PUBMED_FETCH_XML)],
    }


# ── Normalización por cliente ───────────────────────────────────────────────

def test_openalex_normaliza_y_descarta_lo_incompleto():
    p = openalex.parse(OPENALEX_JSON)
    assert [c.title for c in p.candidates] == ["Array programming with NumPy", "Sin DOI pero con id"]
    assert p.dropped == 2
    c = p.candidates[0]
    assert c.doi == "10.1038/s41586-020-2649-2"  # minúsculas, sin prefijo
    assert (c.source_db, c.source_id, c.year, c.publication_date) == ("openalex", "W2741809807", 2020, "2020-09-16")
    assert c.authors == ("Charles R. Harris", "K. Jarrod Millman")
    assert c.journal == "Nature" and c.abstract == "Array programming is powerful"
    assert c.open_access_url == "https://europepmc.org/articles/pmc7759461?pdf=render"
    assert p.candidates[1].doi is None and p.candidates[1].source_id == "W1"
    assert p.candidates[1].open_access_url is None


def test_crossref_normaliza():
    p = crossref.parse(CROSSREF_JSON)
    assert p.dropped == 1 and len(p.candidates) == 2
    c = p.candidates[0]
    assert c.doi == "10.1126/science.1259855" and c.source_id == "10.1126/SCIENCE.1259855"
    assert c.title == "The Genome of a Mammal"
    assert c.authors == ("Ada Lovelace", "The Consortium")
    assert (c.year, c.publication_date, c.journal) == (2015, "2015-03-05", "Science")
    assert c.abstract == "Un & resumen con etiquetas."
    assert c.open_access_url is None  # Crossref no lo informa de forma fiable
    assert p.candidates[1].publication_date == "2001"


def test_semantic_scholar_normaliza():
    p = semantic_scholar.parse(S2_JSON)
    assert p.dropped == 1 and len(p.candidates) == 1
    c = p.candidates[0]
    assert c.doi == "10.5555/3295222.3295349" and c.source_id.startswith("649def34")
    assert (c.year, c.publication_date, c.journal) == (2017, "2017-06-12", "NIPS")
    assert c.open_access_url == "https://arxiv.org/pdf/1706.03762.pdf"


def test_arxiv_normaliza():
    import xml.etree.ElementTree as ET

    p = arxiv.parse(ET.fromstring(ARXIV_XML))
    assert p.dropped == 1 and len(p.candidates) == 2  # la entrada de error se descarta
    a, b = p.candidates
    assert a.title == "Attention Is All You Need" and a.abstract == "The dominant sequence transduction models."
    assert a.source_id == "1706.03762"  # sin versión
    assert a.doi == "10.48550/arxiv.1706.03762"
    assert a.open_access_url == "http://arxiv.org/pdf/1706.03762v7"
    assert (a.year, a.publication_date) == (2017, "2017-06-12")
    assert b.doi == "10.1000/j.real.1" and b.journal == "Phys. Rev. D 1" and b.source_id == "hep-th/9901001"
    assert b.open_access_url is None


def test_pubmed_normaliza():
    assert pubmed.parse_ids(PUBMED_SEARCH_JSON) == ["31452104"]
    # El DOCTYPE de efetch (sin entidades propias) es legítimo.
    p = pubmed.parse_articles(xml_root(Resp(text=PUBMED_FETCH_XML)))
    assert p.dropped == 1 and len(p.candidates) == 1
    c = p.candidates[0]
    assert c.title == "Efecto de algo en algo." and c.source_id == "31452104"
    assert c.doi == "10.1016/s0140-6736(19)31234-5"
    assert c.authors == ("Ana Garcia", "Grupo X")
    assert (c.year, c.publication_date, c.journal) == (2019, "2019-08-07", "The Lancet")
    assert c.abstract == "Primera parte. Segunda."
    assert c.url == "https://pubmed.ncbi.nlm.nih.gov/31452104/"


def test_el_nombre_de_cada_base_es_un_source_db_de_la_biblioteca():
    from app.models.library_document import SourceDB

    validos = {m.value for m in SourceDB}
    assert set(KNOWN_SOURCES) <= validos
    assert DEFAULT_SOURCES == ("openalex", "crossref")


def test_normalize_doi_es_el_de_la_biblioteca_y_el_de_la_compuerta():
    from app.models.library_document import normalize_doi as de_biblioteca
    from app.platform.publication_gate.reference_resolver import normalize_doi as de_compuerta

    for crudo in ["10.1/ABC", " https://doi.org/10.1/ABC ", "doi: 10.1/abc", "http://dx.doi.org/10.1/Abc"]:
        assert normalize_doi(crudo) == de_biblioteca(crudo) == de_compuerta(crudo) == "10.1/abc"
    assert normalize_doi("") is None and normalize_doi(None) is None


# ── Falla cerrada ───────────────────────────────────────────────────────────

def test_sin_titulo_o_sin_identificacion_no_hay_candidato():
    assert build_candidate("openalex", title="", doi="10.1/x") is None
    assert build_candidate("openalex", title="T") is None
    assert build_candidate("openalex", title="T", doi="10.1/x") is not None
    assert build_candidate("openalex", title="T", source_id="W1") is not None


def test_ningun_candidato_puede_nacer_verificado():
    c = build_candidate("crossref", title="T", doi="10.1/x")
    assert c.verified is False and c.as_dict()["verified"] is False
    with pytest.raises(TypeError):
        Candidate(title="T", source_db="crossref", verified=True)


@pytest.mark.asyncio
async def test_ningun_candidato_sale_verificado_de_ninguna_base():
    r = await search_literature("numpy", list(KNOWN_SOURCES), config=CFG, fetch=FakeApi(_bien()), sleep=Pausas())
    assert r.candidates and all(c.verified is False for c in r.candidates)
    assert {c.source_db for c in r.candidates} == set(KNOWN_SOURCES)


# ── Flujo completo, por safe_get con quien="literature_discovery" ───────────

@pytest.mark.asyncio
async def test_consulta_por_defecto_openalex_y_crossref_con_quien_y_sin_datos_del_usuario():
    api = FakeApi(_bien())
    r = await search_literature("  numpy   arrays ", config=CFG, fetch=api, sleep=Pausas())
    assert [x.db for x in r.reports] == ["openalex", "crossref"] and r.complete
    assert {c["host"] for c in api.llamadas} == {"api.openalex.org", "api.crossref.org"}
    assert all(c["quien"] == "literature_discovery" for c in api.llamadas)
    assert api.llamadas[0]["params"]["search"] == "numpy arrays"
    assert api.llamadas[0]["params"]["per-page"] == 5
    assert all("mailto" not in (c["params"] or {}) for c in api.llamadas)  # sin correo configurado
    assert all(c["headers"]["User-Agent"] == "AlejandrIA-LiteratureDiscovery/1.0" for c in api.llamadas)
    assert r.reports[0].count == 2 and r.reports[0].dropped == 2


@pytest.mark.asyncio
async def test_el_correo_de_contacto_es_el_configurado_no_uno_inventado():
    api = FakeApi(_bien())
    cfg = LiteratureConfig(contact_email="plataforma@ejemplo.org", retries=0)
    await search_literature("x", ["openalex", "crossref", "pubmed"], config=cfg, fetch=api, sleep=Pausas())
    por_host = {c["host"]: c for c in api.llamadas}
    assert por_host["api.openalex.org"]["params"]["mailto"] == "plataforma@ejemplo.org"
    assert "mailto:plataforma@ejemplo.org" in por_host["api.crossref.org"]["headers"]["User-Agent"]
    assert por_host["eutils.ncbi.nlm.nih.gov"]["params"]["email"] == "plataforma@ejemplo.org"


@pytest.mark.asyncio
async def test_pubmed_hace_dos_peticiones_y_la_segunda_solo_lleva_los_pmid():
    api = FakeApi(_bien())
    r = await search_literature("lancet", ["pubmed"], config=CFG, fetch=api, sleep=Pausas())
    assert len(api.llamadas) == 2 and len(r.candidates) == 1
    assert api.llamadas[0]["params"]["term"] == "lancet"
    assert api.llamadas[1]["params"]["id"] == "31452104" and "term" not in api.llamadas[1]["params"]


@pytest.mark.asyncio
@pytest.mark.parametrize("consulta", ["", "   ", "palabra " * 80])
async def test_la_consulta_vacia_o_con_forma_de_texto_se_rechaza_sin_salir(consulta):
    api = FakeApi(_bien())
    with pytest.raises(LiteratureQueryError):
        await search_literature(consulta, config=CFG, fetch=api, sleep=Pausas())
    assert api.llamadas == []


@pytest.mark.asyncio
async def test_una_base_desconocida_se_rechaza_antes_de_salir():
    api = FakeApi(_bien())
    with pytest.raises(UnknownSourceError):
        await search_literature("x", ["openalex", "scopus"], config=CFG, fetch=api, sleep=Pausas())
    assert api.llamadas == []


# ── AC10: reintentos, límite de tasa, resultado parcial ─────────────────────

@pytest.mark.asyncio
async def test_reintenta_con_espera_exponencial_y_se_recupera():
    pausas = Pausas()
    api = FakeApi({"api.crossref.org": [Resp(503), Resp(500), Resp(json_body=CROSSREF_JSON)]})
    r = await search_literature("x", ["crossref"], config=CFG, fetch=api, sleep=pausas)
    assert r.complete and r.reports[0].attempts == 3
    assert pausas.valores == [1.0, 2.0]


@pytest.mark.asyncio
async def test_429_respeta_retry_after_con_tope():
    pausas = Pausas()
    api = FakeApi({"api.crossref.org": [Resp(429, headers={"retry-after": "7"}),
                                        Resp(429, headers={"retry-after": "9999"}),
                                        Resp(json_body=CROSSREF_JSON)]})
    r = await search_literature("x", ["crossref"], config=CFG, fetch=api, sleep=pausas)
    assert r.complete and pausas.valores == [7.0, 30.0]


@pytest.mark.asyncio
@pytest.mark.parametrize("respuesta,tipo", [
    (httpx.ReadTimeout("lento"), "timeout"),
    (httpx.ConnectError("sin red"), "network"),
    (Resp(429), "rate_limited"),
    (Resp(502), "http_error"),
    (Resp(200, text="<html>no soy json</html>"), "invalid_response"),
    (Resp(200, json_body={"otra": "forma"}), "invalid_response"),
])
async def test_agotados_los_reintentos_el_error_es_claro_y_especifico(respuesta, tipo):
    pausas = Pausas()
    api = FakeApi({"api.openalex.org": respuesta})
    r = await search_literature("x", ["openalex"], config=CFG, fetch=api, sleep=pausas)
    informe = r.reports[0]
    assert (informe.status, informe.error_kind, informe.attempts) == ("failed", tipo, 3)
    assert "openalex" in informe.message and "3 intento" in informe.message
    assert r.candidates == [] and r.all_failed and not r.complete
    assert len(pausas.valores) == 2 and len(api.llamadas) == 3


@pytest.mark.asyncio
async def test_un_4xx_no_se_reintenta():
    pausas = Pausas()
    api = FakeApi({"api.crossref.org": Resp(400)})
    r = await search_literature("x", ["crossref"], config=CFG, fetch=api, sleep=pausas)
    assert r.reports[0].error_kind == "http_error" and "400" in r.reports[0].message
    assert len(api.llamadas) == 1 and pausas.valores == []


@pytest.mark.asyncio
async def test_un_destino_bloqueado_por_egress_no_se_reintenta():
    api = FakeApi({"api.crossref.org": egress.EgressBlocked("'api.crossref.org' no está en la allowlist")})
    r = await search_literature("x", ["crossref"], config=CFG, fetch=api, sleep=Pausas())
    assert r.reports[0].error_kind == "blocked" and len(api.llamadas) == 1


@pytest.mark.asyncio
async def test_el_fallo_de_una_base_no_tumba_a_las_demas_y_se_ve():
    api = FakeApi({"api.openalex.org": Resp(503), "api.crossref.org": Resp(json_body=CROSSREF_JSON)})
    r = await search_literature("x", ["openalex", "crossref"], config=CFG, fetch=api, sleep=Pausas())
    assert not r.complete and not r.all_failed
    assert [(x.db, x.status) for x in r.reports] == [("openalex", "failed"), ("crossref", "ok")]
    assert [x.db for x in r.failed] == ["openalex"]
    assert {c.source_db for c in r.candidates} == {"crossref"}


@pytest.mark.asyncio
async def test_semantic_scholar_sin_clave_se_omite_con_aviso_y_sin_salir_a_la_red():
    api = FakeApi(_bien())
    cfg = LiteratureConfig(retries=0, semantic_scholar_key="")
    r = await search_literature("x", ["semantic_scholar", "crossref"], config=cfg, fetch=api, sleep=Pausas())
    omitida = r.skipped[0]
    assert (omitida.db, omitida.status, omitida.error_kind) == ("semantic_scholar", "skipped", "missing_api_key")
    assert "SEMANTIC_SCHOLAR_API_KEY" in omitida.message
    assert {c["host"] for c in api.llamadas} == {"api.crossref.org"}
    assert not r.complete  # una base omitida no se confunde con «todo bien»


@pytest.mark.asyncio
async def test_semantic_scholar_con_clave_la_envia_en_cabecera_no_en_la_url():
    api = FakeApi(_bien())
    await search_literature("x", ["semantic_scholar"], config=CFG, fetch=api, sleep=Pausas())
    llamada = api.llamadas[0]
    assert llamada["headers"]["x-api-key"] == "clave-de-prueba"
    assert "clave-de-prueba" not in llamada["url"] and "clave-de-prueba" not in json.dumps(llamada["params"])


@pytest.mark.asyncio
async def test_xml_con_entidades_se_rechaza():
    malo = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><feed xmlns="http://www.w3.org/2005/Atom">&a;</feed>'
    api = FakeApi({"export.arxiv.org": Resp(text=malo)})
    r = await search_literature("x", ["arxiv"], config=LiteratureConfig(retries=0), fetch=api, sleep=Pausas())
    assert r.reports[0].error_kind == "invalid_response"


@pytest.mark.asyncio
async def test_por_defecto_sale_por_egress_safe_get(monkeypatch):
    """Sin `fetch` inyectado, la petición pasa por `egress.safe_get` con `quien` fijo."""
    vistas = []

    async def falso(url, **kw):
        vistas.append((url, kw["quien"]))
        return Resp(json_body=CROSSREF_JSON)

    monkeypatch.setattr(egress, "safe_get", falso)
    r = await search_literature("x", ["crossref"], config=LiteratureConfig(retries=0))
    assert r.complete and vistas == [("https://api.crossref.org/works", "literature_discovery")]


# ── AC1: allowlist solo para esta capacidad ─────────────────────────────────

@pytest.fixture
def publico(monkeypatch):
    monkeypatch.setattr(egress.socket, "getaddrinfo",
                        lambda host, port, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))])


def _allowlist(monkeypatch, valor):
    from app.core.config import settings

    monkeypatch.setattr(settings, "EGRESS_ALLOWED_DOMAINS", valor, raising=False)


@pytest.mark.parametrize("host", list(egress.HOSTS_LITERATURA))
def test_con_allowlist_los_hosts_de_las_bases_se_abren_solo_para_esta_capacidad(monkeypatch, publico, host):
    _allowlist(monkeypatch, "otro.org")
    url = f"https://{host}/x"
    assert egress.is_egress_allowed(url, quien="literature_discovery").allowed
    # ni la herramienta del modelo ni un `quien` cualquiera ganan acceso por esto
    assert not egress.is_egress_allowed(url, quien="egress").allowed
    assert not egress.is_egress_allowed(url, quien="fetch_url").allowed
    if host not in egress.HOSTS_COMPUERTA:
        assert not egress.is_egress_allowed(url, quien="publication_gate").allowed


def test_la_capacidad_no_abre_otros_hosts_ni_gana_los_del_resto(monkeypatch, publico):
    _allowlist(monkeypatch, "otro.org")
    assert not egress.is_egress_allowed("https://api.datacite.org/dois", quien="literature_discovery").allowed
    assert not egress.is_egress_allowed("https://evil.example/", quien="literature_discovery").allowed
    assert egress.is_egress_allowed("https://api.datacite.org/dois", quien="publication_gate").allowed


def test_sin_allowlist_sigue_bloqueando_lo_interno_para_esta_capacidad(monkeypatch):
    _allowlist(monkeypatch, "")
    monkeypatch.setattr(egress.socket, "getaddrinfo",
                        lambda host, port, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))])
    d = egress.is_egress_allowed("https://api.openalex.org/works", quien="literature_discovery")
    assert not d.allowed and "loopback" in d.reason


def test_la_url_de_cada_cliente_esta_en_los_hosts_permitidos():
    urls = [openalex.URL, crossref.URL, semantic_scholar.URL, arxiv.URL, pubmed.ESEARCH, pubmed.EFETCH]
    assert {httpx.URL(u).host for u in urls} == set(egress.HOSTS_LITERATURA)
    assert all(u.startswith("https://") for u in urls)


# ── Test estructural: nada de clientes HTTP propios ─────────────────────────

def test_el_paquete_no_abre_clientes_http_ni_desactiva_tls():
    culpables = []
    for fichero in LIT_DIR.glob("*.py"):
        for nodo in ast.walk(ast.parse(fichero.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Call):
                objetivo = ast.unparse(nodo.func)
                if any(x in objetivo for x in ("AsyncClient", "httpx.Client", "httpx.get", "httpx.post",
                                               "requests.", "urlopen")):
                    culpables.append(f"{fichero.name}:{nodo.lineno} {objetivo}")
                for palabra in nodo.keywords:
                    if palabra.arg == "verify" and isinstance(palabra.value, ast.Constant) and palabra.value.value is False:
                        culpables.append(f"{fichero.name}:{nodo.lineno} verify=False")
    assert culpables == [], culpables


def test_el_unico_punto_de_salida_es_safe_get():
    fuente = (LIT_DIR / "transport.py").read_text(encoding="utf-8")
    assert "egress.safe_get(" in fuente and "QUIEN_LITERATURA" in fuente
    for fichero in LIT_DIR.glob("*.py"):
        if fichero.name != "transport.py":
            assert "safe_get" not in fichero.read_text(encoding="utf-8"), fichero.name


def test_el_paquete_no_depende_de_la_compuerta():
    for fichero in LIT_DIR.glob("*.py"):
        assert "publication_gate" not in "\n".join(
            l for l in fichero.read_text(encoding="utf-8").splitlines() if l.lstrip().startswith(("import", "from"))
        ), fichero.name


# ── Registro de capacidades ─────────────────────────────────────────────────

def test_la_capacidad_esta_registrada_y_resuelve():
    cap = registry.get("literature")
    assert cap.kind is registry.CapabilityKind.LITERATURE and cap.available
    assert cap.resolve() is search_literature
    assert bind(["literature"]).get("literature") is search_literature


# ── `research.sources` en template.yaml ─────────────────────────────────────

def _plantilla(tmp_path, cambio):
    raiz = tmp_path / "proyecto"
    shutil.copytree(loader.PROJECTS_ROOT / "alejandria-magazine", raiz)
    ruta = raiz / loader.PLANTILLA
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    cambio(datos)
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True), encoding="utf-8")
    return raiz


def test_alejandria_declara_openalex_y_crossref():
    assert loader.load("alejandria-magazine").research.sources == ("openalex", "crossref")


def test_sin_bloque_research_se_usan_las_de_por_defecto(tmp_path):
    raiz = _plantilla(tmp_path, lambda d: d.pop("research"))
    assert loader.load_from(raiz).research.sources == DEFAULT_SOURCES


def test_se_pueden_activar_arxiv_pubmed_y_semantic_scholar(tmp_path):
    raiz = _plantilla(tmp_path, lambda d: d["research"].update(sources=["OpenAlex", "arxiv", "pubmed", "semantic_scholar"]))
    assert loader.load_from(raiz).research.sources == ("openalex", "arxiv", "pubmed", "semantic_scholar")


@pytest.mark.parametrize("fuentes,fragmento", [
    (["openalex", "scopus"], "scopus"),
    ([], "no vacía"),
    ("openalex", "lista"),
    (["openalex", "openalex"], "repite"),
    ([1], "nombres"),
])
def test_una_base_mal_escrita_falla_al_cargar_la_plantilla(tmp_path, fuentes, fragmento):
    raiz = _plantilla(tmp_path, lambda d: d["research"].update(sources=fuentes))
    with pytest.raises(TemplateError) as exc:
        loader.load_from(raiz)
    assert fragmento in str(exc.value)


def test_el_bloque_research_rechaza_claves_desconocidas_y_formas_raras(tmp_path):
    for malo, fragmento in [({"sources": ["openalex"], "min_sources": 3}, "min_sources"),
                            ("texto", "mapa")]:
        raiz = _plantilla(tmp_path / str(len(fragmento)), lambda d: d.update(research=malo))
        with pytest.raises(TemplateError) as exc:
            loader.load_from(raiz)
        assert fragmento in str(exc.value)
    with pytest.raises(ResearchConfigError):
        parse_research([])
    assert parse_research(None).sources == DEFAULT_SOURCES


def test_semantic_scholar_en_sources_carga_sin_clave(tmp_path, monkeypatch):
    """La plantilla no cambia de validez según el entorno: sin clave se omite al ejecutar."""
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    raiz = _plantilla(tmp_path, lambda d: d["research"].update(sources=["semantic_scholar"]))
    assert loader.load_from(raiz).research.sources == ("semantic_scholar",)


# ── Configuración ───────────────────────────────────────────────────────────

def test_la_configuracion_sale_de_settings_y_las_claves_no_vienen_del_yaml(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "SEMANTIC_SCHOLAR_API_KEY", " k ")
    monkeypatch.setattr(settings, "LITERATURE_RETRIES", 4)
    cfg = LiteratureConfig.from_settings()
    assert cfg.semantic_scholar_key == "k" and cfg.retries == 4
    assert "SEMANTIC_SCHOLAR_API_KEY" not in (ROOT_DIR / "config.yaml").read_text(encoding="utf-8")


def test_el_env_example_documenta_las_variables_sin_valor():
    texto = (ROOT_DIR / ".env.example").read_text(encoding="utf-8")
    for variable in ("SEMANTIC_SCHOLAR_API_KEY", "LITERATURE_CONTACT_EMAIL", "NCBI_API_KEY"):
        lineas = [l for l in texto.splitlines() if variable in l and "=" in l]
        assert lineas and all(l.split("=", 1)[1].strip() == "" for l in lineas), variable
