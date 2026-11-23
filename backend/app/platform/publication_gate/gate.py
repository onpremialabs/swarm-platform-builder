"""La compuerta: ejecuta los criterios en orden y compone el informe (SPEC-032 AC5).

Se evalúa sobre el **texto final** (el que se publicaría) y no nombra agentes ni
disciplinas: lo que se aplica y con qué parámetros lo declara el proyecto.
Orden (FW §20, los criterios sin LLM primero): 1) resolver y enriquecer las
referencias, 2) validar su estructura, 3) marcadores, 4) estructura IMRaD,
5) retractaciones (si el proyecto las declara), 6) criterios `not_implemented`.
"""
from dataclasses import dataclass, field
from datetime import datetime
import logging
from typing import Any

from app.platform.metrics import observe_gate_criterion

from app.platform.publication_gate.citation_support import check_citation_support
from app.platform.publication_gate.config import GateConfig
from app.platform.publication_gate.explain import explain
from app.platform.publication_gate.placeholders import check_placeholders
from app.platform.publication_gate.reference_resolver import check_reference_existence
from app.platform.publication_gate.references import check_reference_structure
from app.platform.publication_gate.retractions import check_retractions
from app.platform.publication_gate.structure import check_structure
from app.platform.publication_gate.types import CriterionResult


logger = logging.getLogger(__name__)


@dataclass
class GateReport:
    criteria: list
    #: Fuentes tras resolver y enriquecer; las que usa el resto de la compuerta.
    sources: list = field(default_factory=list)
    #: Criterios declarados sin dato todavía: `{"id", "phase"}`. No bloquean.
    pending: list = field(default_factory=list)
    #: criterio → agente responsable (`gate.responsible`).
    responsible: dict = field(default_factory=dict)
    #: criterio → `{"summary", "actions"}` (ver `explain.py`).
    explanations: dict = field(default_factory=dict)

    @property
    def blockers(self) -> list:
        return [c for c in self.criteria if c.blocking]

    @property
    def passed(self) -> bool:
        return not self.blockers

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "criteria": [
                {
                    "criterion": c.criterion,
                    "status": c.status.value,
                    "evidence": c.evidence,
                    # A quién se devuelve si bloquea (AC14); la Fase 2 lo automatizará.
                    "responsible_agent": self.responsible.get(c.criterion),
                    **self.explanations.get(c.criterion, {"summary": {"code": c.criterion}, "actions": []}),
                }
                for c in self.criteria
            ],
            "pending": self.pending,
        }


async def evaluate_gate(
    text: str,
    sources: list,
    config: GateConfig,
    *,
    created_at: datetime | None = None,
    now: datetime | None = None,
    citations: list | None = None,
    **resolver_kwargs: Any,
) -> GateReport:
    """`created_at` es el dato de creación del artículo (lo pasa el servicio; la
    compuerta no conoce agentes ni modelos) y sirve a la comprobación de fechas."""
    existence, enriched = await check_reference_existence(
        sources, config.references, **resolver_kwargs
    )
    criteria: list[CriterionResult] = [
        existence,
        check_reference_structure(enriched),
        check_placeholders(
            text, config.placeholders, dates=config.dates, created_at=created_at, now=now
        ),
        check_structure(text, config.sections, config.titles),
    ]
    if config.citation_support_min_overlap is not None:
        # `citations=None` (no se pudo leer el mapa) -> not_verified, no se omite.
        criteria.append(check_citation_support(text, citations, config.citation_support_min_overlap))
    if config.retractions is not None:
        # Sobre las fuentes ya resueltas (con DOI); sale por la misma puerta de egress.
        criteria.append(await check_retractions(
            enriched, config.retractions, config.references,
            **{k: v for k, v in resolver_kwargs.items() if k in ("fetch", "sleep", "clock")},
        ))
    pending = [{"id": p.id, "phase": p.phase} for p in config.pending]
    for c in criteria:
        observe_gate_criterion(c.criterion, c.status.value)
        logger.info(
            "Compuerta: %s → %s", c.criterion, c.status.value,
            extra={"event": "gate_criterion", "criterion": c.criterion, "status": c.status.value},
        )
    return GateReport(
        criteria=criteria, sources=enriched, pending=pending, responsible=dict(config.responsible),
        explanations=explain(criteria, enriched, config.sections, config.responsible),
    )
