"""Abstención con evidencia insuficiente (SPEC-034 / T22.5 / AC7).

Con menos de N fuentes verificadas por encima del umbral de similitud, el Investigador no
produce texto: se abstiene. La regresión que esto caza es la contraria a la habitual —un
agente que **sí** responde cuando no debería—, y se ve fácil mal: la síntesis desde
conocimiento paramétrico está bien escrita y parece investigación.

Lee `expect.abstain` (true/false) y la **decisión** del paso, que sale por el mismo lector
que la traza (`explainability.decision_of`): si la abstención cambia de forma, cambia en un
sitio. Con `abstain: true` exige además que no haya salida de texto ni citas.
"""
from __future__ import annotations

from evals.agent_behavior.metrics import Metric, register
from evals.agent_behavior.models import CaseResult, EvalCase, MetricResult

NOMBRE = "abstention"


def _evaluar(caso: EvalCase, resultado: CaseResult) -> MetricResult:
    esperada = bool((caso.expect or {}).get("abstain"))
    decision = resultado.decision or {}
    se_abstuvo = bool(decision.get("abstained"))
    texto = (resultado.output or "").strip()

    if esperada:
        if not se_abstuvo:
            return MetricResult(
                name=NOMBRE, score=0.0, passed=False,
                detail="con evidencia insuficiente debía abstenerse y no declaró abstención",
            )
        if texto:
            return MetricResult(
                name=NOMBRE, score=0.0, passed=False,
                detail="declaró abstención pero produjo texto: no debe sintetizar sin evidencia",
            )
        return MetricResult(name=NOMBRE, score=100.0, passed=True,
                            detail="se abstuvo y no produjo texto")
    if se_abstuvo:
        return MetricResult(
            name=NOMBRE, score=0.0, passed=False,
            detail="con evidencia suficiente no debía abstenerse",
        )
    return MetricResult(name=NOMBRE, score=100.0, passed=True,
                        detail="con evidencia suficiente investigó")


register(Metric(
    name=NOMBRE,
    description="Se abstiene (sin texto) con evidencia insuficiente y no se abstiene con suficiente.",
    run=_evaluar,
    applies_to=lambda caso: "abstain" in (caso.expect or {}),
))
