"""Soporte de cada cita por su fragmento (SPEC-035 / T23.7 / AC8).

`citation_fidelity` pregunta si lo citado **existe**; esta pregunta si lo citado **sustenta
la frase**. Un Redactor puede citar `[F2]` —un fragmento real— junto a una afirmación que ese
fragmento no dice, y la fidelidad lo da por bueno.

No reimplementa el criterio: reutiliza `check_citation_support` (T23.3), el mismo de la
compuerta de publicación, de modo que el harness mide lo que la compuerta bloquea. Es
determinista (solape de palabras, sin juez) y falla cerrada: sin citas, con un marcador sin
fragmento o con solape bajo, no pasa.

Cómo reconstruye las citas: el `corpus` del caso son los **fragmentos** (`doc_id`,
`chunk_index`, `text`); con `assign_cite_ids` se les da el mismo alias `F#` que el Redactor, y
con `extract_citations` se leen las del texto. En `live`, el caso fija ese mapa en
`input.citation_map` para que el Redactor use los mismos alias.

Lee `expect.citation_support` (objeto): `min_overlap` (por defecto el de la compuerta) y
`min_score` (por defecto 100: ninguna cita con objeción).
"""
from __future__ import annotations

from evals.agent_behavior.metrics import Metric, register
from evals.agent_behavior.models import CaseResult, EvalCase, MetricResult

NOMBRE = "citation_support"


def _evaluar(caso: EvalCase, resultado: CaseResult) -> MetricResult:
    from app.platform import citations
    from app.platform.publication_gate import citation_support as soporte

    cfg = caso.expect.get("citation_support")
    cfg = cfg if isinstance(cfg, dict) else {}
    min_overlap = float(cfg.get("min_overlap", soporte.DEFAULT_MIN_OVERLAP))
    min_score = float(cfg.get("min_score", 100.0))

    mapa = citations.assign_cite_ids(caso.corpus)
    leidas = citations.extract_citations(resultado.output or "", mapa)
    enlaces = [
        {"citation_key": c["cite_id"], "claim": c.get("claim"), "doc_id": c.get("doc_id"),
         "excerpt": c.get("extract")}
        for c in leidas["citations"]
    ]
    veredicto = soporte.check_citation_support(resultado.output or "", enlaces, min_overlap)

    if not enlaces:
        return MetricResult(
            name=NOMBRE, score=0.0, passed=False,
            detail="el texto no contiene ninguna cita [F#] que contrastar (falla cerrada)",
        )
    # Cada cita se puntúa una vez: una cita con objeción cuenta como no soportada.
    con_objecion = {e.get("citation_key") for e in veredicto.evidence if e.get("citation_key")}
    total = len({e["citation_key"] + "|" + (e["claim"] or "") for e in enlaces})
    malas = {
        k + "|" + (e["claim"] or "")
        for e in enlaces for k in [e["citation_key"]] if k in con_objecion
    }
    score = round(100.0 * (total - len(malas)) / total, 2)
    motivos = sorted({f"{e.get('citation_key')}: {e['reason']}" for e in veredicto.evidence if "reason" in e})
    detalle = (
        f"{total - len(malas)} de {total} cita(s) sin objeción"
        + (f"; {', '.join(motivos[:5])}" if motivos else "")
    )
    # `passed` exige además que la compuerta no tenga nada que objetar a **ningún** marcador:
    # un `[F9]` sin mapa no es una cita leída, pero sí una objeción (reason=unmapped).
    return MetricResult(
        name=NOMBRE, score=score, passed=score >= min_score and not veredicto.evidence, detail=detalle,
    )


register(Metric(
    name=NOMBRE,
    description="Porcentaje de citas [F#] cuyo fragmento sustenta la frase (criterio de la compuerta, T23.3).",
    run=_evaluar,
    applies_to=lambda caso: isinstance(caso.expect.get("citation_support"), dict),
))
