"""Solo se cita lo verificado (SPEC-034 / T22.5 / AC5, ADR-0011).

`citation_fidelity` pregunta si lo citado **existe**; esta pregunta si lo citado **está
verificado**. Son distintas: un documento subido existe en el corpus y, sin DOI verificado,
no puede figurar en `sources` ni en Referencias, y no hay excepción para un «documento
interno». Es la regresión que un cambio de prompt o de filtro produce sin que el texto
se note distinto.

Determinista: cada documento del corpus declara `verified` (true/false) y la métrica
comprueba que cada `[Fuente: X]` de la salida corresponda a uno verificado.
"""
from __future__ import annotations

import re

from evals.agent_behavior.metrics import Metric, register, skipped
from evals.agent_behavior.models import CaseResult, EvalCase, MetricResult

NOMBRE = "source_verification"

_MARCADOR_FUENTE = re.compile(r"\[Fuente:\s*([^\]]+)\]")


def _etiquetas(documento: dict) -> set[str]:
    return {
        str(documento.get(clave) or "").strip().lower()
        for clave in ("doc_title", "title", "filename")
        if str(documento.get(clave) or "").strip()
    }


def _evaluar(caso: EvalCase, resultado: CaseResult) -> MetricResult:
    citas = [c.strip() for c in _MARCADOR_FUENTE.findall(resultado.output or "")]
    if not citas:
        return skipped(NOMBRE, "la salida no cita ninguna fuente")

    verificadas: set[str] = set()
    for documento in caso.corpus:
        if documento.get("verified") is True:
            verificadas |= _etiquetas(documento)
    sin_verificar = [cita for cita in citas if cita.lower() not in verificadas]
    puntuacion = 100.0 * (len(citas) - len(sin_verificar)) / len(citas)
    if sin_verificar:
        detalle = (
            f"{len(sin_verificar)} de {len(citas)} cita(s) no son de un documento con DOI "
            f"verificado: {', '.join(sorted(set(sin_verificar))[:5])}"
        )
    else:
        detalle = f"las {len(citas)} cita(s) son de documentos con DOI verificado"
    return MetricResult(name=NOMBRE, score=round(puntuacion, 2), passed=not sin_verificar, detail=detalle)


register(Metric(
    name=NOMBRE,
    description="Porcentaje de citas de la salida que son de documentos con DOI verificado.",
    run=_evaluar,
    applies_to=lambda caso: bool((caso.expect or {}).get("verified_only")) and bool(caso.corpus),
))
