"""Retractaciones y expresiones de preocupación (SPEC-035 AC5, FW V11).

Para cada referencia con DOI se lee el registro de Crossref y se mira `updated-by`,
donde Crossref (con los datos de Retraction Watch y de las editoriales) anota los
avisos que otras publicaciones hacen sobre la obra. Determinista y **sin LLM**.

Decisiones (ADR-0011):

* **Falla cerrada.** Si Crossref no responde (red, 5xx, 429, JSON inválido, tiempo
  agotado), la referencia queda `not_verified` y bloquea: no se aprueba una cita
  porque nadie dijo que estuviera retractada.
* **Severidad configurable** (`gate.retractions`): `block` o `warn` por tipo de
  aviso. `warn` no bloquea, pero el aviso queda en la evidencia del informe.
* **Solo sale el DOI** de la referencia, por `egress.safe_get` con
  `quien="publication_gate"`. En la evidencia nunca se guarda el texto de una
  excepción (puede llevar la URL consultada).
* Un DOI que Crossref no conoce (404) no se juzga aquí: lo cubre
  `reference_existence` (o es un DOI de DataCite, p. ej. arXiv, que no figura en Crossref).
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable
from urllib.parse import quote

from app.platform.publication_gate.reference_resolver import (
    CROSSREF,
    DATACITE_PREFIXES,
    GATE_METRICS,
    ResolverConfig,
    Unavailable,
    _default_fetch,
    normalize_doi,
    open_session,
)
from app.platform.publication_gate.references import is_citable
from app.platform.publication_gate.types import CriterionResult, CriterionStatus

CRITERION = "retractions"

#: Tipos de `updated-by` de Crossref → categoría de aviso.
RETRACTED_TYPES = frozenset({"retraction", "withdrawal", "removal"})
CONCERN_TYPES = frozenset({"expression_of_concern"})

SEVERITIES = ("block", "warn")

_NO_RESPONDE = object()


@dataclass(frozen=True)
class RetractionConfig:
    """Qué hace la compuerta con cada aviso. Declararla en `gate.retractions` la activa."""

    #: Obra retractada, retirada o eliminada.
    retracted: str = "block"
    #: Expresión de preocupación (la obra sigue publicada, pero con una duda abierta).
    concern: str = "warn"


def classify(record: dict) -> list[dict]:
    """Avisos del registro de Crossref: `[{"kind", "type", "notice_doi", "source", "date"}]`."""
    avisos: list[dict] = []
    for upd in record.get("updated-by") or []:
        if not isinstance(upd, dict):
            continue
        tipo = str(upd.get("type") or "").strip().lower().replace("-", "_")
        if tipo in RETRACTED_TYPES:
            kind = "retracted"
        elif tipo in CONCERN_TYPES:
            kind = "concern"
        else:
            continue
        parts = ((upd.get("updated") or {}).get("date-parts") or [[]])[0]
        avisos.append({
            "kind": kind,
            "type": tipo,
            "notice_doi": normalize_doi(str(upd.get("DOI") or "")),
            "source": str(upd.get("source") or ""),
            "date": "-".join(
                f"{p:02d}" if i else str(p) for i, p in enumerate(parts) if isinstance(p, int)
            ),
        })
    return avisos


async def check_retractions(
    sources: Iterable[dict[str, Any]],
    cfg: RetractionConfig = RetractionConfig(),
    resolver: ResolverConfig = ResolverConfig(),
    *,
    fetch: Callable[..., Awaitable[Any]] = _default_fetch,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> CriterionResult:
    """Un `CriterionResult` para todas las referencias citables con DOI.

    Evidencia: una entrada por aviso (`severity` `block`|`warn`) o por referencia que no
    se pudo comprobar (`status: not_verified`). Con solo avisos `warn` el criterio pasa.
    """
    sess = open_session(resolver, fetch=fetch, sleep=sleep, clock=clock, metrics=GATE_METRICS)
    evidence: list[dict] = []
    worst = CriterionStatus.PASSED
    vistos: dict[str, Any] = {}
    index = 0

    def no_verificada(base: dict, motivo: str) -> None:
        nonlocal worst
        evidence.append({**base, "status": "not_verified", "reason": motivo})
        if worst is CriterionStatus.PASSED:
            worst = CriterionStatus.NOT_VERIFIED

    for src in sources or []:
        if not is_citable(src):
            continue
        index += 1
        doi = normalize_doi(str(src.get("doi", "")))
        if not doi or doi.startswith(DATACITE_PREFIXES):
            continue
        base = {"index": index, "title": str(src.get("title", "")) or "(sin título)", "doi": doi}
        if doi not in vistos:
            try:
                if sess.expired():
                    raise Unavailable("tiempo máximo de evaluación agotado")
                vistos[doi] = await sess.get_json(f"{CROSSREF}/{quote(doi, safe='/')}")
            except Unavailable:
                # Sin el texto de la excepción: puede llevar la URL consultada.
                vistos[doi] = _NO_RESPONDE
        data = vistos[doi]
        if data is _NO_RESPONDE:
            no_verificada(base, "crossref_unavailable")
            continue
        if data is None:
            continue
        message = data.get("message")
        if not isinstance(message, dict):
            no_verificada(base, "crossref_bad_response")
            continue
        for aviso in classify(message):
            severity = cfg.retracted if aviso["kind"] == "retracted" else cfg.concern
            evidence.append({**base, **aviso, "severity": severity})
            if severity == "block":
                worst = CriterionStatus.FAILED
    return CriterionResult(CRITERION, worst, evidence)
