"""EDD de soporte de citas (SPEC-035 / T23.7 / AC8).

Los datasets son `handwritten`: demuestran que la métrica `citation_support` distingue lo que
sustenta una frase de lo que no, no que el modelo se comporte así. Ver
`evals/agent_behavior/README.md`.
"""
import pytest

from evals.agent_behavior import loader, providers, runner
from evals.agent_behavior.metrics import get


def _por_caso(informe):
    return {c.case_id: {m.name: m for m in c.metrics} for c in informe.cases}


@pytest.mark.asyncio
async def test_golden_de_soporte_pasa_entero():
    informe = await runner.run("redactor-citation-support", mode="replay")
    assert informe.passed
    assert informe.scores()["citation_support"] == 100.0


@pytest.mark.asyncio
async def test_regressions_fallan_por_citation_support():
    informe = await runner.run("redactor-citation-support-regressions", mode="replay")
    assert not informe.passed
    por_caso = _por_caso(informe)
    assert set(por_caso) == {
        "cita-fuera-de-tema", "marcador-inventado", "fragmento-sin-texto",
        "texto-sin-citas", "una-de-dos-sin-respaldo",
    }
    for caso, metricas in por_caso.items():
        assert metricas["citation_support"].passed is False, caso
    assert por_caso["una-de-dos-sin-respaldo"]["citation_support"].score == 50.0
    assert por_caso["texto-sin-citas"]["citation_support"].score == 0.0


@pytest.mark.asyncio
async def test_la_metrica_se_salta_en_casos_que_no_la_declaran():
    informe = await runner.run("redactor-golden", mode="replay")
    for caso in informe.cases:
        m = next(x for x in caso.metrics if x.name == "citation_support")
        assert m.skipped_reason is not None


def test_datasets_declaran_procedencia_handwritten_y_no_son_golden_del_gate():
    for nombre in ("redactor-citation-support", "redactor-citation-support-regressions"):
        assert loader.load_by_id(nombre).provenance == "handwritten"
        assert not nombre.endswith("-golden")


def test_el_mapa_del_caso_coincide_con_el_que_la_metrica_reconstruye():
    """En `live` el Redactor parte de `input.citation_map`: debe ser el de la metrica."""
    from app.platform import citations

    for nombre in ("redactor-citation-support", "redactor-citation-support-regressions"):
        for caso in loader.load_by_id(nombre).cases:
            assert caso.input["citation_map"] == citations.assign_cite_ids(caso.corpus)
            assert caso.input.get("project_id")


def test_modo_live_usa_el_agente_real_y_la_metrica_lee_su_texto():
    """No se llama al modelo: se comprueba que `live` construye el proveedor de plataforma y
    que la metrica puntua el texto que este devuelva igual que en `replay`."""
    assert providers.build("live", "redactor").mode == "live"
    caso = loader.load_by_id("redactor-citation-support").cases[0]
    from evals.agent_behavior.models import CaseResult

    ok = get("citation_support").run(caso, CaseResult(case_id=caso.id, agent="redactor",
                                                       output=caso.recorded_output))
    mal = get("citation_support").run(caso, CaseResult(case_id=caso.id, agent="redactor",
                                                        output="Algo ajeno al corpus [F1]."))
    assert ok.passed and not mal.passed
