"""SPEC-035 AC5 / T23.5 — retractaciones y expresiones de preocupación vía Crossref.

El `fetch` es simulado: ningún test sale a la red. Las respuestas imitan la forma real de
`updated-by` en la API de Crossref.
"""
import asyncio
from pathlib import Path

import pytest

from app.platform.publication_gate import CriterionStatus
from app.platform.publication_gate.config import GateConfigError, parse_gate
from app.platform.publication_gate.explain import explain
from app.platform.publication_gate.gate import evaluate_gate
from app.platform.publication_gate.reference_resolver import CROSSREF, ResolverConfig
from app.platform.publication_gate.retractions import (
    RetractionConfig,
    check_retractions,
    classify,
)


class Resp:
    def __init__(self, status=200, data=None, bad_json=False):
        self.status_code, self._data, self._bad = status, data, bad_json

    def json(self):
        if self._bad:
            raise ValueError("no json")
        return self._data


def aviso(tipo, doi="10.1/aviso", source="retraction-watch"):
    return {"DOI": doi, "type": tipo, "source": source, "label": tipo.title(),
            "updated": {"date-parts": [[2023, 5, 4]]}}


def registro(*avisos):
    return Resp(200, {"message": {"DOI": "x", "updated-by": list(avisos)}})


class Fake:
    def __init__(self, por_doi):
        self.por_doi, self.calls = por_doi, []

    async def __call__(self, url, *, params=None, headers=None, timeout=10.0):
        self.calls.append(url)
        assert url.startswith(CROSSREF + "/")
        r = self.por_doi[url[len(CROSSREF) + 1:]]
        if isinstance(r, Exception):
            raise r
        return r


async def _nosleep(_):
    pass


def src(doi, title="T"):
    return {"title": title, "authors": "A, B.", "year": "2020", "journal": "J", "doi": doi}


def run(sources, fake, cfg=RetractionConfig(), resolver=ResolverConfig(retries=0)):
    return asyncio.run(check_retractions(sources, cfg, resolver, fetch=fake, sleep=_nosleep))


def test_sin_avisos_pasa():
    res = run([src("10.1/a")], Fake({"10.1/a": registro()}))
    assert res.status is CriterionStatus.PASSED and not res.evidence


def test_retractada_bloquea_y_deja_evidencia():
    res = run([src("10.1/a")], Fake({"10.1/a": registro(aviso("retraction"))}))
    assert res.status is CriterionStatus.FAILED and res.blocking
    e = res.evidence[0]
    assert (e["kind"], e["severity"], e["doi"], e["notice_doi"], e["date"]) == (
        "retracted", "block", "10.1/a", "10.1/aviso", "2023-05-04")


def test_expresion_de_preocupacion_avisa_por_defecto_sin_bloquear():
    res = run([src("10.1/a")], Fake({"10.1/a": registro(aviso("expression_of_concern"))}))
    assert res.status is CriterionStatus.PASSED and not res.blocking
    assert res.evidence[0]["kind"] == "concern" and res.evidence[0]["severity"] == "warn"


def test_severidad_configurable():
    fake = Fake({"10.1/a": registro(aviso("expression_of_concern")), "10.1/b": registro(aviso("retraction"))})
    res = run([src("10.1/a")], fake, RetractionConfig(concern="block"))
    assert res.status is CriterionStatus.FAILED
    res = run([src("10.1/b")], fake, RetractionConfig(retracted="warn"))
    assert res.status is CriterionStatus.PASSED and res.evidence[0]["severity"] == "warn"


def test_otros_tipos_de_actualizacion_se_ignoran():
    res = run([src("10.1/a")], Fake({"10.1/a": registro(aviso("correction"), aviso("new_version"))}))
    assert res.status is CriterionStatus.PASSED and not res.evidence


def test_retiradas_cuentan_como_retractadas():
    assert [a["kind"] for a in classify({"updated-by": [aviso("withdrawal"), aviso("removal")]})] == [
        "retracted", "retracted"]


@pytest.mark.parametrize("respuesta", [
    Resp(500), Resp(429), Resp(200, bad_json=True), Resp(200, ["no", "dict"]),
    Resp(200, {"sin": "message"}), TimeoutError("https://api.crossref.org/works/x?mailto=a@b.c"),
])
def test_si_crossref_no_responde_falla_cerrada_sin_filtrar_url(respuesta):
    res = run([src("10.1/a")], Fake({"10.1/a": respuesta}))
    assert res.status is CriterionStatus.NOT_VERIFIED and res.blocking
    assert res.evidence[0]["reason"] in ("crossref_unavailable", "crossref_bad_response")
    assert "http" not in str(res.evidence) and "@" not in str(res.evidence)


def test_una_retractada_pesa_mas_que_una_no_verificada():
    fake = Fake({"10.1/a": Resp(500), "10.1/b": registro(aviso("retraction"))})
    assert run([src("10.1/a"), src("10.1/b")], fake).status is CriterionStatus.FAILED


def test_doi_desconocido_sin_doi_y_datacite_no_se_juzgan_aqui():
    fake = Fake({"10.1/a": Resp(404)})
    res = run([src("10.1/a"), {**src(""), "doi": ""}, src("10.48550/arxiv.1")], fake)
    assert res.status is CriterionStatus.PASSED and fake.calls == [f"{CROSSREF}/10.1/a"]


def test_un_doi_repetido_se_consulta_una_vez():
    fake = Fake({"10.1/a": registro(aviso("retraction"))})
    res = run([src("10.1/a"), src("https://doi.org/10.1/A")], fake)
    assert len(fake.calls) == 1 and len(res.evidence) == 2


# ── Compuerta, configuración y explicación ──────────────────────────────────


def test_config_valida_severidades():
    assert parse_gate({}).retractions is None
    assert parse_gate({"retractions": {"concern": "block"}}).retractions == RetractionConfig(concern="block")
    for malo in ({"retracted": "ignore"}, {"otra": "block"}):
        with pytest.raises(GateConfigError):
            parse_gate({"retractions": malo})
    with pytest.raises(GateConfigError):
        parse_gate({"retractions": ["block"]})


def test_la_plantilla_de_alejandria_activa_el_criterio():
    from app.modules.agents.domain import alejandria

    cfg = alejandria.package().gate
    assert cfg.retractions == RetractionConfig(retracted="block", concern="warn")
    assert cfg.responsible["retractions"] == "investigador"


def test_la_compuerta_solo_evalua_el_criterio_si_se_declara():
    fake = Fake({"10.1/a": registro(aviso("retraction"))})
    texto = "# T\n"

    base = parse_gate({})
    rep = asyncio.run(evaluate_gate(texto, [], base, fetch=fake, sleep=_nosleep))
    assert "retractions" not in [c.criterion for c in rep.criteria]
    cfg = parse_gate({"retractions": {}, "references": {"retries": 0}})
    rep = asyncio.run(evaluate_gate(texto, [], cfg, fetch=fake, sleep=_nosleep))
    assert rep.criteria[-1].criterion == "retractions"


def test_explicacion_y_acciones():
    res = run([src("10.1/a"), src("10.1/b")], Fake({
        "10.1/a": registro(aviso("retraction")), "10.1/b": registro(aviso("expression_of_concern"))}))
    ex = explain([res], [], [], {"retractions": "investigador"})["retractions"]
    assert ex["summary"] == {"code": "retractions", "retracted": 1, "concern": 1, "unchecked": 0, "warnings": 1}
    assert {"action": "rerun_agent", "agent": "investigador"} in ex["actions"]


def test_la_salida_pasa_por_la_puerta_de_egress():
    fuente = (Path(__file__).resolve().parents[1] / "app/platform/publication_gate/retractions.py").read_text(encoding="utf-8")
    assert "httpx" not in fuente and "_default_fetch" in fuente
