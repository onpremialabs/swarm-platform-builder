"""Detector de marcadores de posición en el texto final (SPEC-032 AC1, FW V01).

Determinista y sin LLM. Se ignora el código delimitado (``` ```) y en línea
(`` ` ``): un manuscrito que *habla de* un marcador puede citarlo entre comillas
de código.
"""
import re
import re._constants as _c
import re._parser as _p
from datetime import datetime

from app.platform.publication_gate.dates import DateRules, find_out_of_range_dates
from app.platform.publication_gate.types import CriterionResult, CriterionStatus

CRITERION = "placeholders"

# Lista cerrada de AC1. Se amplía en `template.yaml` (`gate.placeholders`).
DEFAULT_PLACEHOLDERS: tuple[str, ...] = (
    "(Author, Year)",
    "(Autor, Año)",
    "(Author et al., Year)",
    "[?]",
    "[??]",
    "[citation needed]",
    "[cita necesaria]",
    "TODO",
    "TBD",
    "XXX",
)

#: Prefijo que distingue una expresión regular de un literal (SPEC-037 AC2).
REGEX_PREFIX = "regex:"
MAX_REGEX_LEN = 200
#: Repeticiones acotadas mayores que esto se consideran un coste desmedido.
MAX_REPEAT_BOUND = 1000


class MarkerError(ValueError):
    """Un marcador de `gate.placeholders` que no se puede aceptar."""


def _subpatterns(av):
    if isinstance(av, _p.SubPattern):
        yield av
    elif isinstance(av, (tuple, list)):
        for x in av:
            yield from _subpatterns(x)


def _audit(sub, in_repeat: bool) -> None:
    """Rechaza lo que puede dar backtracking exponencial o no tiene sentido aquí.

    Es una comprobación **conservadora y estática**: repetición no acotada dentro de
    otra (`(a+)+`), alternativas dentro de una repetición (`(a|a)*`), referencias
    hacia atrás y condicionales. Un patrón legítimo que caiga aquí se reescribe sin
    anidar; mejor rechazar al cargar que colgar la compuerta al publicar.
    """
    for op, av in sub:
        if op in (_c.GROUPREF, _c.GROUPREF_EXISTS):
            raise MarkerError("no se admiten referencias hacia atrás ni condicionales")
        repeats = op in (_c.MAX_REPEAT, _c.MIN_REPEAT, _c.POSSESSIVE_REPEAT)
        multi = False
        if repeats:
            _lo, hi, _body = av
            multi = hi > 1
            if hi != _c.MAXREPEAT and hi > MAX_REPEAT_BOUND:
                raise MarkerError(f"repetición acotada demasiado grande ({hi})")
            if multi and in_repeat:
                raise MarkerError("repeticiones anidadas (riesgo de backtracking catastrófico)")
        if op == _c.BRANCH and in_repeat:
            raise MarkerError("alternativas dentro de una repetición (riesgo de backtracking)")
        for child in _subpatterns(av):
            _audit(child, in_repeat or multi)


def compile_regex_marker(marker: str) -> re.Pattern:
    """Compila `regex:<patrón>` o lanza `MarkerError`. Distingue mayúsculas; para lo
    contrario, `(?i)` al principio del patrón."""
    body = marker[len(REGEX_PREFIX):]
    if not body.strip():
        raise MarkerError("la expresión regular está vacía")
    if len(body) > MAX_REGEX_LEN:
        raise MarkerError(f"la expresión regular supera {MAX_REGEX_LEN} caracteres")
    try:
        parsed = _p.parse(body)
        compiled = re.compile(body)
    except (re.error, RecursionError, OverflowError) as exc:
        raise MarkerError(f"expresión regular no válida: {exc}") from exc
    _audit(parsed, False)
    if compiled.search(""):
        raise MarkerError("la expresión regular casa con el texto vacío (marcaría todo)")
    return compiled


def validate_marker(marker: str) -> None:
    """Valida un marcador al cargar la plantilla: un literal no vacío o una regex sana."""
    if not isinstance(marker, str) or not marker.strip():
        raise MarkerError("el marcador debe ser un texto no vacío")
    if marker.startswith(REGEX_PREFIX):
        compile_regex_marker(marker)


_FENCE = re.compile(r"```.*?(?:```|\Z)", re.DOTALL)
_INLINE = re.compile(r"`[^`\n]*`")


def _blank_code(text: str) -> str:
    """Sustituye el código por espacios, conservando longitudes y saltos de línea,
    para que las posiciones sigan siendo las del texto original."""

    def blank(m: re.Match) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    return _INLINE.sub(blank, _FENCE.sub(blank, text))


def _pattern(marker: str) -> re.Pattern:
    if marker.startswith(REGEX_PREFIX):
        return compile_regex_marker(marker)
    escaped = re.escape(marker)
    if marker[0].isalnum():
        # Las palabras (TODO, TBD, XXX) cuentan enteras y en mayúsculas: «todo el
        # mundo» es español corriente, no un marcador.
        return re.compile(rf"(?<!\w){escaped}(?!\w)")
    return re.compile(escaped, re.IGNORECASE)


def check_placeholders(
    text: str,
    markers: tuple[str, ...] | list[str] = DEFAULT_PLACEHOLDERS,
    *,
    dates: DateRules | None = None,
    created_at: datetime | None = None,
    now: datetime | None = None,
) -> CriterionResult:
    """Marcadores literales y `regex:`; y, si el proyecto lo declara (`gate.dates`) y
    se conoce la creación del artículo, fechas de metadatos fuera de rango."""
    visible = _blank_code(text or "")
    evidence: list[dict] = []
    if dates is not None and dates.labels:
        evidence.extend(find_out_of_range_dates(visible, dates, created_at, now))
    for marker in markers:
        for m in _pattern(marker).finditer(visible):
            line = visible.count("\n", 0, m.start()) + 1
            col = m.start() - (visible.rfind("\n", 0, m.start()) + 1) + 1
            evidence.append(
                {"pattern": marker, "offset": m.start(), "line": line, "column": col}
            )
    evidence.sort(key=lambda e: e["offset"])
    status = CriterionStatus.FAILED if evidence else CriterionStatus.PASSED
    return CriterionResult(CRITERION, status, evidence)
