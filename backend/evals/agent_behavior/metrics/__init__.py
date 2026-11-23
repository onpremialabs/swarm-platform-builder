"""Métricas de comportamiento y su registro (SPEC-014 / T9.3 / AC3).

Una métrica recibe un caso y lo que el agente produjo, y devuelve una puntuación
de 0 a 100 con un motivo. La escala única no es cosmética: hace comparables
métricas de naturalezas distintas —«¿cita fuentes que existen?» y «¿cabe en el
presupuesto de tokens?»— y permite declarar umbrales en T9.5 sin traducir
unidades en cada una.

Se registran por nombre para que añadir una métrica sea añadir un módulo, no
editar el runner. `applies_to` decide si la métrica tiene algo que decir sobre un
caso: una métrica que no aplica se **salta con motivo** en vez de puntuar 100,
que sería mentir con buena nota.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from evals.agent_behavior.models import CaseResult, EvalCase, MetricResult

#: Firma de una métrica: (caso, resultado parcial) → resultado de la métrica.
MetricFn = Callable[[EvalCase, CaseResult], MetricResult]


@dataclass(frozen=True)
class Metric:
    name: str
    description: str
    run: MetricFn
    #: Qué necesita el caso para que la métrica tenga sentido.
    applies_to: Callable[[EvalCase], bool] = lambda _caso: True


_REGISTRO: Dict[str, Metric] = {}


def register(metric: Metric) -> Metric:
    _REGISTRO[metric.name] = metric
    return metric


def get(name: str) -> Metric:
    try:
        return _REGISTRO[name]
    except KeyError as error:
        disponibles = ", ".join(sorted(_REGISTRO)) or "(ninguna)"
        raise KeyError(
            f"No existe la métrica '{name}'. Registradas: {disponibles}"
        ) from error


def all_metrics() -> List[Metric]:
    return [_REGISTRO[nombre] for nombre in sorted(_REGISTRO)]


def skipped(name: str, reason: str) -> MetricResult:
    """Resultado de una métrica que no aplica a este caso."""
    return MetricResult(name=name, score=0.0, passed=True, skipped_reason=reason)


def _cargar_incorporadas() -> None:
    # Import perezoso para evitar el ciclo módulo↔registro.
    from evals.agent_behavior.metrics import (  # noqa: F401
        abstention, budget, calibration, citation_support, citations, coherence, format_compliance,
        reference_completeness, source_verification,
    )


_cargar_incorporadas()
