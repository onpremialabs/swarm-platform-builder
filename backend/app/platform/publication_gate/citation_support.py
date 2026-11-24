"""Criterio de soporte de cada cita (SPEC-035 / T23.3 / AC2, AC4).

Determinista y sin LLM: el juez de modelo es T23.4. Aquí solo se decide lo que se
puede decidir sin interpretar nada:

* **Sin fragmento** (AC2): una cita sin documento o sin extracto no se puede
  contrastar -> `not_verified`, y bloquea (falla cerrada, ADR-0011). La confirmación
  manual del autor **no** la rescata: no hay pasaje que contrastar.
* **Solape bajo** (AC4): fracción de las palabras con contenido de la afirmación que
  aparecen en el extracto. Por debajo del umbral configurable (`min_overlap`) la cita
  se marca `needs_human_review` sin esperar al juez; bloquea hasta que el autor la
  confirma (`confirmed_at` en `citation_links`, que registra quién y cuándo).
* **Marcador sin mapa**: un `[F#]` del texto sin fila en el mapa, un texto sin
  ninguna cita o un mapa que no se pudo leer, tampoco se aprueban.

Un solape alto no demuestra el soporte: solo lo deja pasar al juez (T23.4,
`citation_judge.py`). Sin juez declarado, `passed` significa «nada determinista que
objetar»; con juez (`judge_required`), exige además su veredicto.

Limitación: se compara contra el `excerpt` guardado (inicio del fragmento,
`EXTRACT_CHARS`), no contra el fragmento completo; un solape bajo puede ser un falso
positivo, y por eso es revisión humana y no rechazo.
"""
import re
import unicodedata
from typing import Any, Iterable, Optional

from app.platform.publication_gate.types import CriterionResult, CriterionStatus

CRITERION = "citation_support"
DEFAULT_MIN_OVERLAP = 0.25
_MIN_TOKEN = 4
_STOP = frozenset((
    "para como pero este esta estos estas entre sobre desde hasta cuando donde "
    "which that this with from have been were their there than then into also "
    "such these those while about after before between"
).split())
_WORD = re.compile(r"[a-z0-9]+")
_MARKER = re.compile(r"\[\s*(F\d+(?:\s*[,;]\s*F\d+)*)\s*\]")


def _tokens(text: Optional[str]) -> set[str]:
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return {w for w in _WORD.findall(t) if len(w) >= _MIN_TOKEN and w not in _STOP}


def overlap(claim: Optional[str], excerpt: Optional[str]) -> Optional[float]:
    """Fracción (0..1) de las palabras de la afirmación presentes en el extracto.

    `None` si la afirmación no tiene palabras con contenido (no hay qué comparar).
    """
    palabras = _tokens(claim)
    if not palabras:
        return None
    return len(palabras & _tokens(excerpt)) / len(palabras)


def _get(link: Any, name: str) -> Any:
    return link.get(name) if isinstance(link, dict) else getattr(link, name, None)


def check_citation_support(
    text: str,
    links: Optional[Iterable[Any]],
    min_overlap: float = DEFAULT_MIN_OVERLAP,
    judge_required: bool = False,
) -> CriterionResult:
    """`links`: filas de `citation_links` (o dicts) del texto evaluado; `None` = no se pudo leer.

    `judge_required` (T23.4): el proyecto declaró el juez, así que un solape suficiente ya
    no basta: hace falta su veredicto (`status` de la fila). `unsupported` falla,
    `partial` va a revisión humana y sin veredicto (`not_verified`: el juez no corrió o
    falló) no se aprueba. La confirmación manual del autor los rescata a los tres.
    """
    if links is None:
        return CriterionResult(CRITERION, CriterionStatus.NOT_VERIFIED, [{"problem": "map_unavailable"}])
    filas = list(links)
    evidence: list[dict] = []
    en_texto = {c for m in _MARKER.finditer(text or "") for c in re.findall(r"F\d+", m.group(1))}
    mapeadas = {_get(f, "citation_key") for f in filas}

    if not filas and not en_texto:
        return CriterionResult(CRITERION, CriterionStatus.NOT_VERIFIED, [{"problem": "no_citations"}])
    for cid in sorted(en_texto - mapeadas, key=lambda c: int(c[1:])):
        evidence.append({"citation_key": cid, "reason": "unmapped"})

    for f in filas:
        clave = _get(f, "citation_key")
        extracto = (_get(f, "excerpt") or "").strip()
        base = {"citation_key": clave, "claim_index": _get(f, "claim_index")}
        if not _get(f, "doc_id") or not extracto:
            evidence.append({**base, "reason": "no_fragment"})
            continue
        solape = overlap(_get(f, "claim"), extracto)
        if solape is None:
            evidence.append({**base, "reason": "no_claim"})
        elif solape < min_overlap and _get(f, "confirmed_at") is None:
            evidence.append({
                **base, "reason": "low_overlap", "overlap": round(solape, 3),
                "min_overlap": min_overlap, "needs_human_review": True,
            })
        elif judge_required and _get(f, "confirmed_at") is None:
            veredicto = _get(f, "status") or "not_verified"
            if veredicto == "unsupported":
                evidence.append({**base, "reason": "judge_unsupported", "needs_human_review": True,
                                 "rationale": _get(f, "rationale")})
            elif veredicto == "partial":
                evidence.append({**base, "reason": "judge_partial", "needs_human_review": True,
                                 "rationale": _get(f, "rationale")})
            elif veredicto != "supported":
                evidence.append({**base, "reason": "judge_unavailable"})

    if any(e.get("reason") == "judge_unsupported" for e in evidence):
        status = CriterionStatus.FAILED
    else:
        status = CriterionStatus.NOT_VERIFIED if evidence else CriterionStatus.PASSED
    return CriterionResult(CRITERION, status, evidence)
