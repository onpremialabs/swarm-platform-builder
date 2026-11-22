"""Fechas de metadatos fuera del rango de vida del artículo (SPEC-037 AC2).

Caso real: un manuscrito creado el 15-sep-2026 conservaba «Fecha: Octubre 2023
(Borrador)», inventada por el modelo. Se detecta **sin LLM** y con el mínimo que es
determinista y no da falsos positivos sobre el cuerpo del texto:

- Solo se examinan las líneas de **metadatos**, las que empiezan por una etiqueta que
  declara el proyecto (`gate.dates.labels`: «Fecha», «Date»…) seguida de «:». Una
  fecha dentro de un párrafo o de una cita («(García, 2019)») **no se toca**: un
  artículo cita trabajos de cualquier año.
- Una fecha está **fuera de rango** si termina antes de la creación del artículo
  (menos la tolerancia) o empieza después del día de la evaluación (más la
  tolerancia). Con granularidad de mes o de año se compara el intervalo entero: «2026»
  o «septiembre 2026» no se marcan para un artículo creado en septiembre de 2026.
- Sin `created_at` (evaluación sin artículo) no hay con qué comparar y no se
  comprueba nada; el servicio de la compuerta siempre lo pasa.
"""
import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

_MESES = {
    **{m: i for i, m in enumerate(
        ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"], 1)},
    "setiembre": 9,
    **{m: i for i, m in enumerate(
        ["january", "february", "march", "april", "may", "june", "july", "august",
         "september", "october", "november", "december"], 1)},
}
_M = "|".join(sorted(_MESES, key=len, reverse=True))

_FECHA = re.compile(
    rf"""
    (?P<iso>(?P<iy>\d{{4}})-(?P<im>\d{{2}})(?:-(?P<id>\d{{2}}))?)
    |(?P<sl>(?P<sd>\d{{1,2}})/(?P<sm>\d{{1,2}})/(?P<sy>\d{{4}}))
    |(?P<dmy>(?P<dd>\d{{1,2}})\s+(?:de\s+)?(?P<dm>{_M})\.?,?\s+(?:de\s+|del\s+)?(?P<dy>\d{{4}}))
    |(?P<mdy>(?P<mm>{_M})\.?\s+(?P<md>\d{{1,2}}),?\s+(?P<my>\d{{4}}))
    |(?P<my2>(?P<m2>{_M})\.?,?\s+(?:de\s+|del\s+)?(?P<y2>\d{{4}}))
    |(?<![\d/-])(?P<y>(?:19|20)\d{{2}})(?![\d/-])
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass(frozen=True)
class DateRules:
    """`gate.dates`: sin etiquetas la comprobación está apagada."""

    labels: tuple = ()
    tolerance_days: int = 1


def _tramo(y: int, mo: int, d: int | None) -> tuple[date, date]:
    if d is not None:
        f = date(y, mo, d)
        return f, f
    return date(y, mo, 1), date(y, mo, calendar.monthrange(y, mo)[1])


def _intervalo(m: re.Match) -> tuple[date, date] | None:
    g = m.groupdict()
    try:
        if g["iso"]:
            return _tramo(int(g["iy"]), int(g["im"]), int(g["id"]) if g["id"] else None)
        if g["sl"]:
            return _tramo(int(g["sy"]), int(g["sm"]), int(g["sd"]))
        if g["dmy"]:
            return _tramo(int(g["dy"]), _MESES[g["dm"].lower()], int(g["dd"]))
        if g["mdy"]:
            return _tramo(int(g["my"]), _MESES[g["mm"].lower()], int(g["md"]))
        if g["my2"]:
            return _tramo(int(g["y2"]), _MESES[g["m2"].lower()], None)
        return date(int(g["y"]), 1, 1), date(int(g["y"]), 12, 31)
    except ValueError:
        return None  # 31 de febrero, mes 13…: no es una fecha, no se juzga


def _linea_de_metadatos(labels: tuple) -> re.Pattern:
    etiquetas = "|".join(re.escape(x) for x in sorted(labels, key=len, reverse=True))
    return re.compile(
        rf"^[ \t>*_#\-]*(?:{etiquetas})[ \t*_]*:[ \t*_]*(?P<valor>.*)$",
        re.IGNORECASE | re.MULTILINE,
    )


def find_out_of_range_dates(
    visible: str, rules: DateRules, created_at: datetime | None, now: datetime | None = None
) -> list[dict]:
    if created_at is None or not rules.labels:
        return []
    tol = timedelta(days=rules.tolerance_days)
    desde = created_at.date() - tol
    hasta = (now or datetime.utcnow()).date() + tol
    evidence: list[dict] = []
    for linea in _linea_de_metadatos(rules.labels).finditer(visible):
        base = linea.start("valor")
        for m in _FECHA.finditer(linea.group("valor")):
            tramo = _intervalo(m)
            if tramo is None:
                continue
            inicio, fin = tramo
            if fin < desde:
                motivo = "before_creation"
            elif inicio > hasta:
                motivo = "after_evaluation"
            else:
                continue
            offset = base + m.start()
            line = visible.count("\n", 0, offset) + 1
            col = offset - (visible.rfind("\n", 0, offset) + 1) + 1
            evidence.append({
                "pattern": "date_out_of_range",
                "text": m.group(0),
                "reason": motivo,
                "article_created": created_at.date().isoformat(),
                "offset": offset,
                "line": line,
                "column": col,
            })
    return evidence
