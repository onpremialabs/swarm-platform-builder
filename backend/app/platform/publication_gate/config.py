"""Configuración de la compuerta, declarada por proyecto (`gate:` en `template.yaml`).

Se valida al cargar la plantilla —igual que `graph.flow_rules`—: un proyecto con
una compuerta mal escrita se entera al arrancar, no al publicar.
"""
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.platform.publication_gate.citation_support import DEFAULT_MIN_OVERLAP
from app.platform.publication_gate.dates import DateRules
from app.platform.publication_gate.placeholders import (
    DEFAULT_PLACEHOLDERS,
    MarkerError,
    validate_marker,
)
from app.platform.publication_gate.reference_resolver import ResolverConfig

DEFAULT_SECTIONS = ("introduction", "methods", "results", "discussion", "references")


@dataclass(frozen=True)
class PendingCriterion:
    """Criterio declarado cuyo dato aún no existe: `not_implemented`, no bloquea."""

    id: str
    phase: str


@dataclass(frozen=True)
class GateConfig:
    placeholders: tuple = DEFAULT_PLACEHOLDERS
    #: fechas de metadatos fuera del rango de vida del artículo (SPEC-037 AC2).
    dates: DateRules = field(default_factory=DateRules)
    references: ResolverConfig = field(default_factory=ResolverConfig)
    sections: tuple = DEFAULT_SECTIONS
    titles: Mapping[str, Mapping[str, tuple]] = field(default_factory=dict)
    pending: tuple = ()
    #: criterio → agente al que se devuelve el manuscrito si ese criterio bloquea.
    responsible: Mapping[str, str] = field(default_factory=dict)
    #: umbral de solape afirmacion/fragmento (SPEC-035); `None` = criterio no declarado.
    citation_support_min_overlap: float | None = None


_NUMEROS = {
    "title_similarity": (0.0, 1.0),
    "other_authors_ratio": (0.0, 1.0),
    "timeout_s": (0.1, 600.0),
    "retries": (0, 10),
    "backoff_s": (0.0, 60.0),
    "max_total_s": (1.0, 3600.0),
    "cache_ttl_days": (0.0, 3650.0),
    "candidates": (1, 50),
}


class GateConfigError(ValueError):
    pass


def _exigir(cond: bool, msg: str) -> None:
    if not cond:
        raise GateConfigError(msg)


def parse_gate(raw: Any) -> GateConfig:
    _exigir(isinstance(raw, dict), "'gate' debe ser un mapa")

    marcadores = raw.get("placeholders", list(DEFAULT_PLACEHOLDERS))
    _exigir(
        isinstance(marcadores, list)
        and bool(marcadores)
        and all(isinstance(m, str) and m.strip() for m in marcadores),
        "'gate.placeholders' debe ser una lista no vacía de textos",
    )
    for m in marcadores:
        # Un `regex:` roto o catastrófico se descubre aquí, no al publicar.
        try:
            validate_marker(m)
        except MarkerError as exc:
            raise GateConfigError(f"'gate.placeholders': {m!r}: {exc}") from exc

    fechas = raw.get("dates", {})
    fechas = {} if fechas is None else fechas
    _exigir(isinstance(fechas, dict), "'gate.dates' debe ser un mapa")
    for clave in fechas:
        _exigir(clave in ("labels", "tolerance_days"), f"'gate.dates.{clave}' no es un ajuste conocido")
    etiquetas = fechas.get("labels", [])
    _exigir(
        isinstance(etiquetas, list) and all(isinstance(x, str) and x.strip() for x in etiquetas),
        "'gate.dates.labels' debe ser una lista de textos",
    )
    tolerancia = fechas.get("tolerance_days", 1)
    _exigir(
        isinstance(tolerancia, int) and not isinstance(tolerancia, bool) and 0 <= tolerancia <= 31,
        "'gate.dates.tolerance_days' debe ser un entero entre 0 y 31",
    )

    refs = raw.get("references") or {}
    _exigir(isinstance(refs, dict), "'gate.references' debe ser un mapa")
    valores: dict = {}
    for clave, valor in refs.items():
        _exigir(
            clave in _NUMEROS or clave == "contact_email",
            f"'gate.references.{clave}' no es un ajuste conocido",
        )
        if clave == "contact_email":
            _exigir(isinstance(valor, str), "'gate.references.contact_email' debe ser texto")
        else:
            lo, hi = _NUMEROS[clave]
            _exigir(
                isinstance(valor, (int, float)) and not isinstance(valor, bool) and lo <= valor <= hi,
                f"'gate.references.{clave}' debe ser un número entre {lo} y {hi}, no {valor!r}",
            )
        valores[clave] = valor

    estructura = raw.get("structure") or {}
    _exigir(isinstance(estructura, dict), "'gate.structure' debe ser un mapa")
    secciones = tuple(estructura.get("sections") or DEFAULT_SECTIONS)
    titulos_crudos = estructura.get("titles") or {}
    _exigir(isinstance(titulos_crudos, dict), "'gate.structure.titles' debe ser un mapa por idioma")
    titulos: dict = {}
    for idioma, por_seccion in titulos_crudos.items():
        _exigir(isinstance(por_seccion, dict), f"'gate.structure.titles.{idioma}' debe ser un mapa")
        for s in secciones:
            t = por_seccion.get(s)
            _exigir(
                isinstance(t, list) and bool(t) and all(isinstance(x, str) and x.strip() for x in t),
                f"'gate.structure.titles.{idioma}.{s}' debe ser una lista de títulos",
            )
        titulos[idioma] = {s: tuple(por_seccion[s]) for s in secciones}

    pendientes = []
    for entrada in raw.get("pending") or []:
        _exigir(
            isinstance(entrada, dict) and bool(entrada.get("id")) and bool(entrada.get("phase")),
            "Cada entrada de 'gate.pending' necesita 'id' y 'phase'",
        )
        pendientes.append(PendingCriterion(str(entrada["id"]), str(entrada["phase"])))

    responsable = raw.get("responsible") or {}
    _exigir(
        isinstance(responsable, dict)
        and all(isinstance(k, str) and isinstance(v, str) and v for k, v in responsable.items()),
        "'gate.responsible' debe ser un mapa criterio → agente",
    )

    soporte = raw.get("citation_support")
    umbral = None
    if soporte is not None:
        _exigir(isinstance(soporte, dict), "'gate.citation_support' debe ser un mapa")
        for clave in soporte:
            _exigir(clave == "min_overlap", f"'gate.citation_support.{clave}' no es un ajuste conocido")
        umbral = soporte.get("min_overlap", DEFAULT_MIN_OVERLAP)
        _exigir(
            isinstance(umbral, (int, float)) and not isinstance(umbral, bool) and 0.0 <= umbral <= 1.0,
            f"'gate.citation_support.min_overlap' debe ser un número entre 0 y 1, no {umbral!r}",
        )
        umbral = float(umbral)

    return GateConfig(
        placeholders=tuple(marcadores),
        dates=DateRules(labels=tuple(x.strip() for x in etiquetas), tolerance_days=tolerancia),
        references=ResolverConfig(**valores),
        sections=secciones,
        titles=titulos,
        pending=tuple(pendientes),
        responsible=dict(responsable),
        citation_support_min_overlap=umbral,
    )
