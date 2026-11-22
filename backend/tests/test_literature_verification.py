"""SPEC-034 / T22.2 — verificación de candidatos (AC2, AC10). Sin red real.

El resolver de la compuerta se alimenta con respuestas simuladas de Crossref, OpenAlex y
DataCite. Lo que se vigila: que **solo** se ofrece lo que resuelve y coincide, que cada
descarte lleva su motivo, que un resolver caído nunca verifica (falla cerrada), que la
fecha de corte descarta lo que debe y nada más, que se deduplica sin perder de qué bases
venía, y que la compuerta sigue saliendo como `publication_gate`.
"""
import asyncio
import os
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("SECRET_KEY", "ci-secret-not-for-prod")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_literature.db")

from app.platform import egress  # noqa: E402
from app.platform.capabilities.literature import models as lit_models  # noqa: E402
from app.platform.capabilities.literature import verification as ver  # noqa: E402
from app.platform.capabilities.literature.models import (  # noqa: E402
    BaseReport, LiteratureResult, build_candidate,
)
from app.platform.publication_gate import reference_resolver as rr  # noqa: E402

HOY = datetime(2026, 11, 22, 10, 0)


# ── Simulación del resolver ─────────────────────────────────────────────────

class Resp:
    def __init__(self, status=200, data=None):
        self.status_code, self._data = status, data

    def json(self):
        return self._data


def cr(doi, title, family, year, journal="Nature", type_="journal-article"):
    return {"DOI": doi, "title": [title], "type": type_,
            "author": [{"family": f} for f in family],
            "issued": {"date-parts": [[year]]}, "container-title": [journal]}


def dc(doi, title, family, year):
    return {"data": {"attributes": {
        "doi": doi, "titles": [{"title": title}], "creators": [{"familyName": f} for f in family],
        "publicationYear": year, "publisher": "arXiv", "types": {"resourceTypeGeneral": "Preprint"}}}}


class Fake:
    """`registro`: doi -> Resp para Crossref/DataCite; `busqueda`: items de Crossref por título."""

    def __init__(self, crossref=None, datacite=None, busqueda=None, caido=False):
        self.crossref, self.datacite, self.busqueda = crossref or {}, datacite or {}, busqueda or []
        self.caido, self.calls = caido, []

    async def __call__(self, url, *, params=None, headers=None, timeout=10.0):
        self.calls.append((url, params, headers))
        if self.caido:
            raise ConnectionError("sin red")
        if url.startswith(rr.DATACITE + "/"):
            doi = url[len(rr.DATACITE) + 1:]
            return Resp(200, self.datacite[doi]) if doi in self.datacite else Resp(404)
        if url.startswith(rr.CROSSREF + "/"):
            doi = url[len(rr.CROSSREF) + 1:]
            return Resp(200, {"message": self.crossref[doi]}) if doi in self.crossref else Resp(404)
        if url == rr.CROSSREF:
            return Resp(200, {"message": {"items": self.busqueda}})
        if url == rr.OPENALEX:
            return Resp(200, {"results": []})
        if url.startswith(rr.OPENALEX + "/"):
            return Resp(404)
        raise AssertionError(f"URL inesperada: {url}")


async def _nosleep(_):
    pass


def verificar(candidatos, fake, searched_at=HOY, **kw):
    return asyncio.run(ver.verify_candidates(
        candidatos, searched_at, fetch=fake, sleep=_nosleep,
        resolver=kw.pop("resolver", rr.ResolverConfig(retries=1)), **kw))


def cand(db="openalex", **campos):
    base = dict(title="Deep learning", doi="10.1038/nature14539", source_id="W1",
                authors=["Yann LeCun", "Yoshua Bengio", "Geoffrey Hinton"], year=2015,
                publication_date="2015-05-27", journal="Nature")
    base.update(campos)
    c = build_candidate(db, **base)
    assert c is not None
    return c


NATURE = cr("10.1038/nature14539", "Deep learning", ["LeCun", "Bengio", "Hinton"], 2015)


# ── Verificado correcto ─────────────────────────────────────────────────────

def test_un_candidato_que_resuelve_y_coincide_se_ofrece_como_verificado():
    r = verificar([cand()], Fake({"10.1038/nature14539": NATURE}))
    assert r.verified_count == 1 and not r.discarded
    v = r.verified[0]
    assert v.doi == "10.1038/nature14539" and v.provider == "crossref"
    assert v.verification_method == "doi_resolved" and v.verified_at is not None
    assert v.doi_origin == "declared" and v.found_in == ("openalex",)
    assert v.as_dict()["verified"] is True


def test_el_resultado_conserva_la_fecha_de_la_busqueda():
    assert verificar([cand()], Fake({"10.1038/nature14539": NATURE})).searched_at == HOY


def test_el_doi_se_normaliza_antes_de_resolver():
    fake = Fake({"10.1038/nature14539": NATURE})
    r = verificar([cand(doi="https://doi.org/10.1038/NATURE14539")], fake)
    assert r.verified_count == 1
    assert fake.calls[0][0].endswith("/10.1038/nature14539")


# ── Descartes por resolución ────────────────────────────────────────────────

def test_un_doi_inexistente_se_descarta_como_unresolved():
    r = verificar([cand(doi="10.9999/inventado")], Fake())
    assert r.verified_count == 0
    assert [d.reason for d in r.discarded] == ["unresolved"]
    assert not r.discarded[0].not_verified


def test_un_titulo_que_no_coincide_se_descarta_como_metadata_mismatch():
    r = verificar([cand(title="Un artículo completamente distinto sobre geología")],
                  Fake({"10.1038/nature14539": NATURE}))
    assert [d.reason for d in r.discarded] == ["metadata_mismatch"]
    assert "título" in r.discarded[0].detail


def test_autores_o_anio_que_no_coinciden_tambien_son_mismatch():
    fake = Fake({"10.1038/nature14539": NATURE})
    assert verificar([cand(authors=["Ada Lovelace"])], fake).discarded[0].reason == "metadata_mismatch"
    assert verificar([cand(year=2001, publication_date="2001-01-01")],
                     fake).discarded[0].reason == "metadata_mismatch"


def test_sin_doi_y_sin_autores_con_los_que_buscar_es_no_identifier():
    c = build_candidate("pubmed", title="Algo", source_id="12345")
    r = verificar([c], Fake())
    assert [d.reason for d in r.discarded] == ["no_identifier"]


def test_sin_doi_se_busca_por_titulo_y_autores_y_un_unico_resultado_fiable_lo_verifica():
    fake = Fake(busqueda=[NATURE])
    c = cand(db="pubmed", doi=None, source_id="999")
    r = verificar([c], fake)
    assert r.verified_count == 1
    v = r.verified[0]
    assert v.doi == "10.1038/nature14539" and v.doi_origin == "resolved_by_title"
    assert v.candidate.doi == "10.1038/nature14539"


def test_sin_doi_y_sin_coincidencia_fiable_se_descarta_como_unresolved():
    r = verificar([cand(db="crossref", doi=None, source_id="x")], Fake(busqueda=[]))
    assert [d.reason for d in r.discarded] == ["unresolved"]


def test_arxiv_sin_doi_declarado_deriva_el_doi_de_datacite_y_se_resuelve_ahi():
    doi = "10.48550/arxiv.1706.03762"
    fake = Fake(datacite={doi: dc(doi, "Attention is all you need",
                                  ["Vaswani", "Shazeer", "Parmar"], 2017)})
    c = build_candidate("arxiv", title="Attention is all you need", source_id="1706.03762",
                        authors=["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"], year=2017,
                        publication_date="2017-06-12")
    c = replace(c, doi=None)  # el cliente de arXiv ya lo deriva; aquí se prueba la red de seguridad
    r = verificar([c], fake)
    assert r.verified_count == 1
    assert r.verified[0].doi == doi and r.verified[0].doi_origin == "derived_arxiv"
    assert r.verified[0].provider == "datacite"
    assert fake.calls[0][0] == f"{rr.DATACITE}/{doi}"


def test_arxiv_con_el_doi_que_ya_deriva_el_cliente_se_verifica_en_datacite():
    doi = "10.48550/arxiv.1706.03762"
    fake = Fake(datacite={doi: dc(doi, "Attention is all you need",
                                  ["Vaswani", "Shazeer", "Parmar"], 2017)})
    c = build_candidate("arxiv", title="Attention is all you need", doi=doi,
                        source_id="1706.03762", authors=["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"],
                        year=2017, publication_date="2017-06-12")
    assert verificar([c], fake).verified_count == 1


def test_se_completan_los_metadatos_que_el_candidato_no_traia():
    c = cand(journal=None)
    r = verificar([c], Fake({"10.1038/nature14539": NATURE}))
    assert r.verified[0].candidate.journal == "Nature"
    assert r.verified[0].enriched == ("journal",)


# ── Falla cerrada ───────────────────────────────────────────────────────────

def test_si_el_resolver_esta_caido_el_candidato_no_se_verifica_nunca():
    fake = Fake(caido=True)
    r = verificar([cand(), cand(doi="10.1/b", title="Otro", source_id="W2")], fake)
    assert r.verified_count == 0
    assert {d.reason for d in r.discarded} == {"resolver_unavailable"}
    assert all(d.not_verified for d in r.discarded)
    assert r.unavailable_count == 2 and r.search_status() == "partial"
    assert len(fake.calls) >= 2  # se reintentó (retries=1)


def test_un_429_agotados_los_reintentos_tampoco_verifica():
    class Limitado(Fake):
        async def __call__(self, url, **kw):
            return Resp(429)

    r = verificar([cand()], Limitado())
    assert r.verified_count == 0 and r.discarded[0].reason == "resolver_unavailable"


def test_un_error_inesperado_en_el_resolver_no_verifica(monkeypatch):
    async def roto(*a, **k):
        raise RuntimeError("bug")

    monkeypatch.setattr(ver, "resolve_reference", roto)
    r = verificar([cand()], Fake())
    assert r.verified_count == 0 and r.discarded[0].reason == "resolver_unavailable"


def test_openalex_responde_un_5xx_y_crossref_no_conoce_el_doi_no_se_afirma_que_no_existe():
    class Medio(Fake):
        async def __call__(self, url, **kw):
            if url.startswith(rr.OPENALEX):
                return Resp(503)
            return Resp(404)

    r = verificar([cand()], Medio())
    assert r.discarded[0].reason == "resolver_unavailable"


# ── Duplicados ──────────────────────────────────────────────────────────────

def test_duplicados_por_doi_conservan_el_mas_completo_y_anotan_las_bases():
    pobre = cand(db="crossref", source_id="10.1038/nature14539", journal=None,
                 publication_date=None, authors=["Yann LeCun", "Yoshua Bengio", "Geoffrey Hinton"])
    rico = cand(db="openalex", abstract="Resumen.", url="https://x.org/1")
    fake = Fake({"10.1038/nature14539": NATURE})
    r = verificar([pobre, rico], fake)
    assert r.verified_count == 1
    v = r.verified[0]
    assert v.candidate.source_db == "openalex"
    assert set(v.found_in) == {"openalex", "crossref"}
    assert [d.reason for d in r.discarded] == ["duplicate"]
    assert r.discarded[0].duplicate_of == "10.1038/nature14539"
    assert len(fake.calls) == 1  # un solo DOI, una sola consulta


def test_duplicados_con_el_mismo_nivel_de_metadatos_conservan_el_primero():
    a, b = cand(db="openalex"), cand(db="crossref")
    r = verificar([a, b], Fake({"10.1038/nature14539": NATURE}))
    assert r.verified[0].candidate.source_db == "openalex"
    assert r.verified[0].found_in == ("openalex", "crossref")


def test_el_doi_con_otra_forma_cuenta_como_duplicado():
    a, b = cand(), cand(db="crossref", doi="https://doi.org/10.1038/NATURE14539")
    r = verificar([a, b], Fake({"10.1038/nature14539": NATURE}))
    assert r.verified_count == 1 and r.discarded_counts == {"duplicate": 1}


def test_duplicado_que_solo_se_ve_tras_resolver_por_titulo():
    con_doi = cand(db="openalex")
    sin_doi = cand(db="pubmed", doi=None, source_id="55", abstract="resumen", url="https://p/1")
    r = verificar([con_doi, sin_doi], Fake({"10.1038/nature14539": NATURE}, busqueda=[NATURE]))
    assert r.verified_count == 1 and r.discarded_counts == {"duplicate": 1}
    assert set(r.verified[0].found_in) == {"openalex", "pubmed"}
    assert r.verified[0].candidate.source_db == "pubmed"  # el más completo


# ── Fecha futura ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("fecha,anio,futuro", [
    ("2026-11-23", 2026, True),     # exacta, un día después
    ("2026-11-22", 2026, False),    # el mismo día no es futuro
    ("2026-12", 2026, True),        # mes entero posterior
    ("2026-11", 2026, False),       # el mes en curso: parte del intervalo es anterior
    ("2027", 2027, True),           # año entero posterior
    ("2026", 2026, False),          # el año en curso
    (None, 2027, True),             # sin fecha completa, el año manda
    (None, None, False),            # sin fecha no se descarta por esta regla
    ("2026-02-31", None, False),    # no es una fecha: no se juzga
])
def test_regla_de_fecha_futura(fecha, anio, futuro):
    c = cand(publication_date=fecha, year=anio)
    assert ver.is_future(c, HOY) is futuro


def test_un_candidato_futuro_se_descarta_sin_consultar_la_red():
    fake = Fake({"10.1038/nature14539": NATURE})
    r = verificar([cand(publication_date="2027-01-01", year=2027)], fake)
    assert [d.reason for d in r.discarded] == ["future_date"] and not fake.calls
    assert "2026-11-22" in r.discarded[0].detail


def test_un_candidato_sin_fecha_sigue_su_curso():
    r = verificar([cand(publication_date=None, year=None)], Fake({"10.1038/nature14539": NATURE}))
    assert r.verified_count == 1


def test_el_futuro_no_gana_a_un_duplicado_vigente():
    futuro = cand(db="crossref", publication_date="2027-01-01", year=2027, abstract="x", url="u")
    ok = cand(db="openalex")
    r = verificar([futuro, ok], Fake({"10.1038/nature14539": NATURE}))
    assert r.verified[0].candidate.source_db == "openalex"
    assert r.discarded_counts == {"future_date": 1}


# ── Biblioteca ──────────────────────────────────────────────────────────────

def test_ya_en_biblioteca_se_marca_y_no_se_descarta():
    r = verificar([cand(), cand(doi="10.1/b", title="Otro", source_id="W2")],
                  Fake({"10.1038/nature14539": NATURE,
                        "10.1/b": cr("10.1/b", "Otro", ["LeCun", "Bengio", "Hinton"], 2015)}),
                  library_dois={"https://doi.org/10.1038/NATURE14539"})
    marcas = {v.doi: v.already_in_library for v in r.verified}
    assert marcas == {"10.1038/nature14539": True, "10.1/b": False}


def test_library_dois_of_consulta_la_biblioteca_del_proyecto(monkeypatch):
    from app.platform import library

    visto = []

    async def find(session, project_id, doi):
        visto.append((project_id, doi))
        return object() if doi == "10.1038/nature14539" else None

    monkeypatch.setattr(library, "find_by_doi", find)
    r = asyncio.run(ver.library_dois_of(None, "P1", [cand(), cand(doi="10.1/b", source_id="W2")]))
    assert r == {"10.1038/nature14539"} and {p for p, _ in visto} == {"P1"}


def test_un_verificado_se_convierte_en_documento_candidato_de_la_biblioteca():
    from app.models import LibraryDocumentModel

    v = verificar([cand()], Fake({"10.1038/nature14539": NATURE})).verified[0]
    campos = ver.library_fields(v)
    assert campos["curation_status"] == "candidate" and campos["verified"] is True
    assert campos["verification_method"] == "doi_resolved" and campos["verified_at"] is not None
    doc = LibraryDocumentModel(project_id=None, **campos)  # los enums se validan al construir
    assert doc.doi == "10.1038/nature14539" and doc.source_db == "openalex"


def test_add_candidate_to_library_usa_library_add_document(monkeypatch):
    from app.platform import library

    llamadas = []

    async def add(session, project_id, *, added_by=None, **fields):
        llamadas.append((project_id, added_by, fields))
        return "doc"

    monkeypatch.setattr(library, "add_document", add)
    v = verificar([cand()], Fake({"10.1038/nature14539": NATURE})).verified[0]
    assert asyncio.run(ver.add_candidate_to_library(None, "P1", v, added_by="U")) == "doc"
    assert llamadas[0][0] == "P1" and llamadas[0][2]["doi"] == "10.1038/nature14539"


# ── Alimenta search_logs ────────────────────────────────────────────────────

def test_el_resultado_alimenta_el_registro_de_busqueda():
    from app.models.search_log import SEARCH_STATUSES

    r = verificar(
        [cand(), cand(db="crossref"), cand(doi="10.9/x", title="Falso", source_id="W9"),
         cand(doi="10.1/f", publication_date="2030-01-01", year=2030, source_id="W7")],
        Fake({"10.1038/nature14539": NATURE}))
    campos = r.log_fields()
    assert campos["result_count"] == 4 and campos["verified_count"] == 1
    assert campos["discarded"] == {"duplicate": 1, "unresolved": 1, "future_date": 1}
    assert campos["searched_at"] == HOY and campos["status"] in SEARCH_STATUSES
    assert set(campos["discarded"]) <= set(ver.DISCARD_REASONS)
    assert r.per_source["openalex"] == {"returned": 3, "verified": 1}


def test_el_estado_refleja_las_bases_que_fallaron():
    r = verificar([cand()], Fake({"10.1038/nature14539": NATURE}))
    ok = BaseReport("openalex", "ok", count=1)
    ko = BaseReport("crossref", "failed", error_kind="timeout")
    assert r.search_status(LiteratureResult("q", [], (ok,))) == "completed"
    assert r.search_status(LiteratureResult("q", [], (ok, ko))) == "partial"
    assert r.search_status(LiteratureResult("q", [], (ko,))) == "failed"


# ── Identidad de salida y compuerta intacta ─────────────────────────────────

def test_la_verificacion_sale_por_egress_como_literature_discovery(monkeypatch):
    quienes = []

    async def safe_get(url, *, quien="egress", params=None, headers=None, timeout=10.0, **_):
        quienes.append(quien)
        return Resp(200, {"message": NATURE})

    monkeypatch.setattr(egress, "safe_get", safe_get)
    r = asyncio.run(ver.verify_candidates([cand()], HOY, sleep=_nosleep))
    assert r.verified_count == 1 and quienes == ["literature_discovery"]


def test_la_compuerta_sigue_saliendo_como_publication_gate(monkeypatch):
    quienes = []

    async def safe_get(url, *, quien="egress", params=None, headers=None, timeout=10.0, **_):
        quienes.append(quien)
        return Resp(200, {"message": NATURE})

    monkeypatch.setattr(egress, "safe_get", safe_get)
    sess = rr.open_session(rr.ResolverConfig())
    out = asyncio.run(rr.resolve_reference(sess, {"doi": "10.1038/nature14539", "title": "Deep learning",
                                                  "authors": "LeCun, Bengio, Hinton", "year": "2015"}))
    assert out.status.value == "passed" and quienes == ["publication_gate"]


def test_las_metricas_de_la_compuerta_no_se_tocan_desde_la_verificacion(monkeypatch):
    llamadas = []
    monkeypatch.setattr(rr, "observe_gate_reference", lambda o: llamadas.append(o))
    monkeypatch.setattr(rr, "observe_gate_external_error", lambda p, e: llamadas.append((p, e)))
    verificar([cand(), cand(doi="10.9/x", title="Falso", source_id="W9")],
              Fake({"10.1038/nature14539": NATURE}), cache=rr.PositiveCache())
    verificar([cand()], Fake(caido=True))
    assert llamadas == []


def test_la_compuerta_si_sigue_contando_sus_metricas(monkeypatch):
    llamadas = []
    monkeypatch.setattr(rr, "observe_gate_reference", lambda o: llamadas.append(o))
    fake = Fake({"10.1038/nature14539": NATURE})
    src = {"doi": "10.1038/nature14539", "title": "Deep learning",
           "authors": "LeCun, Bengio, Hinton", "year": "2015"}
    asyncio.run(rr.check_reference_existence([src], rr.ResolverConfig(), fetch=fake, sleep=_nosleep))
    assert llamadas == ["resolved"]


def test_datacite_esta_abierto_para_esta_capacidad_y_solo_para_ella(monkeypatch):
    import socket

    from app.core.config import settings

    monkeypatch.setattr(egress.socket, "getaddrinfo",
                        lambda host, port, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))])
    monkeypatch.setattr(settings, "EGRESS_ALLOWED_DOMAINS", "otro.org", raising=False)
    url = "https://api.datacite.org/dois/10.48550/arxiv.1"
    assert "api.datacite.org" in egress.HOSTS_LITERATURA
    assert egress.is_egress_allowed(url, quien="literature_discovery").allowed
    assert not egress.is_egress_allowed(url, quien="fetch_url").allowed


def test_el_modulo_no_abre_clientes_http_propios():
    fuente = (ROOT_DIR / "app/platform/capabilities/literature/verification.py").read_text(encoding="utf-8")
    assert "httpx" not in fuente and "verify=False" not in fuente


def test_normalize_doi_es_el_mismo_en_la_capacidad_la_compuerta_y_la_biblioteca():
    from app.models.library_document import normalize_doi as de_biblioteca

    for crudo in ("https://doi.org/10.1/ABC", "DOI: 10.1/abc", "  10.1/Abc ", "", None):
        esperado = rr.normalize_doi(crudo or "") or None
        assert lit_models.normalize_doi(crudo) == esperado == de_biblioteca(crudo)
