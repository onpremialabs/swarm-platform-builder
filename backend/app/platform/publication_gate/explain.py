"""Explica cada criterio del informe: qué se comprobó y qué se puede hacer (SPEC-032).

Solo emite **códigos y datos**; el texto para la persona lo pone el frontend (mismo
reparto que los códigos de error de la API). Es determinista y no consulta nada: lo
calcula a partir del resultado del criterio, las fuentes enriquecidas y el texto.

Acciones sugeridas (`action`): `rerun_agent` (devolver el manuscrito al agente
responsable), `provide_doi` (aportar a mano el DOI de una referencia) y `edit_text`
(corregir el texto a mano). Un criterio que supera o que aún no se comprueba no
propone ninguna.
"""
from typing import Mapping, Sequence

from app.platform.publication_gate.references import is_citable
from app.platform.publication_gate.types import CriterionResult, CriterionStatus

#: Tope de referencias que se listan como evidencia de un criterio superado.
MAX_ITEMS = 50


def _citables(sources: Sequence[dict]) -> list[dict]:
    return [s for s in sources or [] if is_citable(s)]


def _item(source: dict) -> dict:
    return {
        "title": str(source.get("title", "") or ""),
        "doi": str(source.get("doi", "") or ""),
        "year": str(source.get("year", "") or ""),
        "journal": str(source.get("journal", "") or ""),
    }


def _summary(c: CriterionResult, sources: Sequence[dict], sections: Sequence[str]) -> dict:
    ok = c.status is CriterionStatus.PASSED
    if c.criterion in ("reference_existence", "reference_structure"):
        citables = _citables(sources)
        malas = {e.get("index") for e in c.evidence}
        buenas = [s for i, s in enumerate(citables, start=1) if i not in malas]
        out = {"code": c.criterion, "total": len(citables), "ok": len(buenas)}
        if ok:
            out["items"] = [_item(s) for s in buenas[:MAX_ITEMS]]
        return out
    if c.criterion == "retractions":
        avisos = [e for e in c.evidence if e.get("kind")]
        return {
            "code": "retractions",
            "retracted": sum(1 for e in avisos if e["kind"] == "retracted"),
            "concern": sum(1 for e in avisos if e["kind"] == "concern"),
            "unchecked": sum(1 for e in c.evidence if e.get("status") == "not_verified"),
            "warnings": sum(1 for e in avisos if e.get("severity") == "warn"),
        }
    if c.criterion == "placeholders":
        return {"code": "placeholders", "found": len(c.evidence)}
    if c.criterion == "citation_support":
        return {
            "code": "citation_support", "found": len(c.evidence),
            "reasons": [e.get("reason") or e.get("problem") for e in c.evidence],
            "needs_human_review": sum(1 for e in c.evidence if e.get("needs_human_review")),
        }
    if c.criterion == "imrad_structure":
        out = {"code": "imrad_structure", "sections": list(sections)}
        if not ok:
            out["problems"] = [e.get("problem") for e in c.evidence if e.get("problem")]
        return out
    return {"code": c.criterion}


def _actions(c: CriterionResult, agent) -> list[dict]:
    if c.status not in (CriterionStatus.FAILED, CriterionStatus.NOT_VERIFIED):
        return []
    out: list[dict] = []
    if c.criterion == "reference_existence":
        out.append({"action": "provide_doi", "targets": [e.get("index") for e in c.evidence]})
    if agent:
        out.append({"action": "rerun_agent", "agent": agent})
    if c.criterion != "reference_existence" or not agent:
        out.append({"action": "edit_text"})
    return out


def explain(
    criteria: Sequence[CriterionResult],
    sources: Sequence[dict],
    sections: Sequence[str],
    responsible: Mapping[str, str],
) -> dict[str, dict]:
    """criterio → `{"summary": {...}, "actions": [...]}`."""
    return {
        c.criterion: {
            "summary": _summary(c, sources, sections),
            "actions": _actions(c, responsible.get(c.criterion)),
        }
        for c in criteria
    }
