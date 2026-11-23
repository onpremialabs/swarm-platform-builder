"""Tipos comunes de la compuerta (SPEC-032 AC5)."""
from dataclasses import dataclass, field
from enum import Enum


class CriterionStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    # Lo que no se puede comprobar no se aprueba (ADR-0011): bloquea.
    NOT_VERIFIED = "not_verified"
    # El dato aún no existe; no bloquea y el informe lo lista como pendiente.
    NOT_IMPLEMENTED = "not_implemented"


BLOCKING_STATUSES = frozenset({CriterionStatus.FAILED, CriterionStatus.NOT_VERIFIED})


@dataclass(frozen=True)
class CriterionResult:
    criterion: str
    status: CriterionStatus
    # Una entrada por hallazgo: patrón, posición, campo que falta, motivo…
    evidence: list[dict] = field(default_factory=list)
    # Modo aviso (p. ej. `CITATION_SUPPORT_ENFORCE=false`): el resultado se conserva y se
    # muestra tal cual (`not_verified` sigue siéndolo), pero no bloquea la publicación.
    advisory: bool = False

    @property
    def blocking(self) -> bool:
        return self.status in BLOCKING_STATUSES and not self.advisory
