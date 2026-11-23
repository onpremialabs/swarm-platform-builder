"""EDD de cobertura bibliográfica sobre papers de acceso abierto (SPEC-034 / T22.9 / AC5, AC7).

Los datasets son `handwritten`: estos tests demuestran que las métricas muerden en los
bordes de la regla (N verificadas, N-1, interno, bajo umbral), no que el modelo se
comporte así. Ver `evals/agent_behavior/README.md`.
"""
import pytest

from evals.agent_behavior import runner


def _por_caso(informe):
    return {c.case_id: {m.name: m for m in c.metrics} for c in informe.cases}


@pytest.mark.asyncio
async def test_cobertura_golden_pasa_entero_y_cubre_los_bordes():
    informe = await runner.run("investigador-cobertura", mode="replay")
    assert informe.passed
    por_caso = _por_caso(informe)
    assert set(por_caso) == {
        "oa-exactamente-n-verificadas",
        "oa-contexto-sin-verificar-no-se-cita",
        "oa-doi-aportado-por-autor-cuenta",
        "abstencion-n-menos-uno-con-interno",
        "abstencion-fuente-bajo-umbral-de-similitud",
        "abstencion-biblioteca-vacia",
    }
    for caso in ("oa-exactamente-n-verificadas", "oa-contexto-sin-verificar-no-se-cita",
                 "oa-doi-aportado-por-autor-cuenta"):
        assert por_caso[caso]["source_verification"].score == 100.0
        assert por_caso[caso]["abstention"].passed
    for caso in ("abstencion-n-menos-uno-con-interno", "abstencion-fuente-bajo-umbral-de-similitud",
                 "abstencion-biblioteca-vacia"):
        assert por_caso[caso]["abstention"].score == 100.0


@pytest.mark.asyncio
async def test_cobertura_regresiones_fallan_por_su_metrica():
    informe = await runner.run("investigador-cobertura-regressions", mode="replay")
    assert not informe.passed
    por_caso = _por_caso(informe)
    assert por_caso["cita-interno-aunque-hay-suficientes"]["source_verification"].passed is False
    assert por_caso["sintetiza-con-n-menos-uno"]["abstention"].passed is False
    assert por_caso["se-abstiene-con-evidencia-suficiente"]["abstention"].passed is False
    assert por_caso["declara-abstencion-pero-escribe"]["abstention"].passed is False


def test_los_datasets_de_cobertura_declaran_procedencia_handwritten():
    from evals.agent_behavior import loader

    for nombre in ("investigador-cobertura", "investigador-cobertura-regressions"):
        assert loader.load_by_id(nombre).provenance == "handwritten"
