"""Carga de proyectos desde el filesystem (SPEC-013 / T8.4 / AC4).

Un proyecto es un directorio con un `template.yaml` y sus `agents/*.agent.md`.
Este módulo lo lee, lo valida y lo traduce a lo que el motor entiende: un
`GraphSpec` y una lista de `AgentSpec`. Con eso, crear un proyecto nuevo es
copiar un directorio y editar un YAML — que es lo que significa «no-code» aquí.

Dos cosas que este módulo arregla y no solo mueve:

**Las rutas.** Había cuatro sitios distintos probando `Path("app/agents")` y
`Path("../app/agents")` a ver cuál existía: el runner genérico, la siembra, el
resolutor de modelos y el router. Eso depende del directorio desde el que se
arranque el proceso, así que el mismo código encuentra los perfiles con
`uvicorn` desde `backend/` y no los encuentra desde la raíz — y cuando no los
encuentra **no falla**: cae a valores por defecto. Aquí la raíz se deriva del
paquete (`__file__`), una sola vez.

**La validación.** Una plantilla que nombra una capacidad inexistente, o cuya
secuencia menciona un agente que no declara, o cuyo perfil no está en disco, se
rechaza **al cargarla**. Sin esto, el error aparece a mitad de la ejecución y
disfrazado de otra cosa.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from app.platform.capabilities.literature.research import (
    ResearchConfig, ResearchConfigError, parse_research,
)
from app.platform.capabilities.registry import get as get_capability
from app.platform.engine.agents import AgentSpec, register_agent
from app.platform.engine.graph import GraphSpec
from app.platform.engine.routing import ReviewLoop
from app.platform.flow_validation import ERROR, NO_RULES, WARNING, FlowRules, Requirement
from app.platform.publication_gate.config import GateConfig, GateConfigError, parse_gate

logger = logging.getLogger(__name__)

#: Raíz de los proyectos, derivada del paquete y no del directorio de trabajo.
#: `app/platform/projects/loader.py` → sube a `backend/` → `backend/projects`.
PROJECTS_ROOT = Path(__file__).resolve().parents[3] / "projects"

PLANTILLA = "template.yaml"
VERSION_SOPORTADA = 1


class TemplateError(ValueError):
    """La plantilla de un proyecto no es utilizable. El mensaje dice por qué."""


@dataclass(frozen=True)
class ProjectPackage:
    """Un proyecto leído del filesystem, ya validado."""

    slug: str
    name: str
    description: str
    use_case_type: str
    root: Path
    agents: Tuple[AgentSpec, ...]
    graph: GraphSpec
    #: nombre de agente → ruta de su `.agent.md`, para la siembra.
    profiles: Dict[str, Path]
    #: reglas de dependencia del Flow Designer (`graph.flow_rules`); sin ellas, solo las estructurales.
    flow_rules: FlowRules = NO_RULES
    #: compuerta de publicación (`gate:`, SPEC-032); `None` si el proyecto no declara una.
    gate: Optional[GateConfig] = None
    #: descubrimiento de literatura (`research:`, SPEC-034); por defecto OpenAlex y Crossref.
    research: ResearchConfig = ResearchConfig()

    def profile_path(self, agent: str) -> Optional[Path]:
        return self.profiles.get(agent)

    def register(self) -> None:
        """Da de alta los agentes del proyecto en el motor. Idempotente."""
        for agente in self.agents:
            register_agent(agente)


# ── Lectura y validación ────────────────────────────────────────────────────

def _exigir(condicion: bool, mensaje: str) -> None:
    if not condicion:
        raise TemplateError(mensaje)


def _leer_yaml(ruta: Path) -> Dict[str, Any]:
    try:
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise TemplateError(f"{ruta} no es YAML válido: {error}") from error
    _exigir(isinstance(datos, dict), f"{ruta} debe contener un mapa en la raíz")
    return datos


def _agentes(datos: Dict[str, Any], raiz: Path) -> Tuple[Tuple[AgentSpec, ...], Dict[str, Path]]:
    crudos = datos.get("agents") or []
    _exigir(isinstance(crudos, list) and crudos, "La plantilla no declara ningún agente")

    especificaciones: List[AgentSpec] = []
    perfiles: Dict[str, Path] = {}
    vistos: set[str] = set()

    for indice, crudo in enumerate(crudos):
        _exigir(isinstance(crudo, dict), f"El agente #{indice + 1} no es un mapa")
        nombre = str(crudo.get("name") or "").strip()
        _exigir(bool(nombre), f"El agente #{indice + 1} no tiene 'name'")
        _exigir(nombre not in vistos, f"El agente '{nombre}' está declarado dos veces")
        vistos.add(nombre)

        entrypoint = str(crudo.get("entrypoint") or "").strip()
        _exigir(":" in entrypoint, f"'{nombre}': 'entrypoint' debe ser 'modulo:atributo'")

        requiere = tuple(crudo.get("requires") or ())
        for capacidad in requiere:
            try:
                get_capability(capacidad)
            except KeyError as error:
                raise TemplateError(
                    f"'{nombre}' pide la capacidad '{capacidad}', que el motor no "
                    "registra. Revisa platform/capabilities/registry.py."
                ) from error

        perfil = crudo.get("profile")
        if perfil:
            ruta_perfil = (raiz / str(perfil)).resolve()
            _exigir(
                ruta_perfil.is_file(),
                f"'{nombre}': el perfil '{perfil}' no existe en {raiz}",
            )
            _exigir(
                raiz.resolve() in ruta_perfil.parents,
                f"'{nombre}': el perfil '{perfil}' apunta fuera del proyecto",
            )
            perfiles[nombre] = ruta_perfil

        especificaciones.append(AgentSpec(
            name=nombre,
            entrypoint=entrypoint,
            requires=requiere,
            description=str(crudo.get("description") or ""),
        ))

    return tuple(especificaciones), perfiles


def _grafo(datos: Dict[str, Any], nombres: set[str]) -> GraphSpec:
    grafo = datos.get("graph") or {}
    _exigir(isinstance(grafo, dict), "'graph' debe ser un mapa")

    secuencia = tuple(grafo.get("sequence") or ())
    _exigir(bool(secuencia), "'graph.sequence' está vacía: un proyecto sin flujo no ejecuta nada")
    for nodo in secuencia:
        _exigir(
            nodo in nombres,
            f"'graph.sequence' nombra a '{nodo}', que no está declarado en 'agents'",
        )

    bucles: List[ReviewLoop] = []
    for crudo in grafo.get("review_loops") or []:
        _exigir(isinstance(crudo, dict), "Cada entrada de 'review_loops' debe ser un mapa")
        revisor = str(crudo.get("reviewer") or "").strip()
        rechazo = str(crudo.get("on_reject") or "").strip()
        _exigir(revisor in nombres, f"El bucle nombra un revisor desconocido: '{revisor}'")
        _exigir(rechazo in nombres, f"El bucle de '{revisor}' rechaza hacia '{rechazo}', que no existe")
        destinos = tuple(crudo.get("retry_targets") or ())
        for destino in destinos:
            _exigir(
                destino in nombres,
                f"El bucle de '{revisor}' reintenta hacia '{destino}', que no existe",
            )
        agotado = str(crudo.get("on_exhausted", "advance"))
        _exigir(
            agotado in ("advance", "stop"),
            f"El bucle de '{revisor}': 'on_exhausted' debe ser 'advance' o 'stop', no {agotado!r}",
        )
        bucles.append(ReviewLoop(
            reviewer=revisor,
            on_reject=rechazo,
            threshold=float(crudo.get("threshold", 80.0)),
            max_loops=int(crudo.get("max_loops", 3)),
            retry_targets=destinos,
            on_exhausted=agotado,
        ))

    return GraphSpec(sequence=secuencia, loops=tuple(bucles))


def _reglas_de_flujo(datos: Dict[str, Any], nombres: set[str]) -> FlowRules:
    crudo = (datos.get("graph") or {}).get("flow_rules") or {}
    _exigir(isinstance(crudo, dict), "'graph.flow_rules' debe ser un mapa")

    huerfanos = crudo.get("orphans", WARNING)
    _exigir(
        huerfanos in (None, ERROR, WARNING),
        f"'flow_rules.orphans' debe ser 'error', 'warning' o null, no {huerfanos!r}",
    )

    requisitos: List[Requirement] = []
    for entrada in crudo.get("requires") or []:
        _exigir(isinstance(entrada, dict), "Cada entrada de 'flow_rules.requires' debe ser un mapa")
        agente = str(entrada.get("agent") or "").strip()
        previos = tuple(entrada.get("any_of") or ())
        gravedad = entrada.get("severity", ERROR)
        _exigir(agente in nombres, f"'flow_rules.requires' nombra a '{agente}', que no está declarado")
        _exigir(bool(previos), f"La regla de '{agente}' no dice qué necesita antes ('any_of')")
        for previo in previos:
            _exigir(previo in nombres, f"La regla de '{agente}' necesita a '{previo}', que no está declarado")
        _exigir(gravedad in (ERROR, WARNING), f"La regla de '{agente}': severidad {gravedad!r} no válida")
        requisitos.append(Requirement(
            agent=agente,
            any_of=previos,
            severity=gravedad,
            satisfied_by_existing_output=bool(entrada.get("satisfied_by_existing_output", False)),
        ))
    return FlowRules(requires=tuple(requisitos), orphans=huerfanos)


def _compuerta(datos: Dict[str, Any], nombres: set) -> Optional[GateConfig]:
    if "gate" not in datos:
        return None
    try:
        config = parse_gate(datos["gate"])
    except GateConfigError as exc:
        raise TemplateError(str(exc)) from exc
    for criterio, agente in config.responsible.items():
        _exigir(
            agente in nombres,
            f"'gate.responsible' manda '{criterio}' a '{agente}', que no está declarado",
        )
    return config


def _investigacion(datos: Dict[str, Any]) -> ResearchConfig:
    try:
        return parse_research(datos.get("research"))
    except ResearchConfigError as exc:
        raise TemplateError(str(exc)) from exc


def load_from(raiz: Path) -> ProjectPackage:
    """Lee y valida el proyecto que hay en `raiz`."""
    plantilla = raiz / PLANTILLA
    _exigir(plantilla.is_file(), f"No hay {PLANTILLA} en {raiz}")

    datos = _leer_yaml(plantilla)
    version = datos.get("version")
    _exigir(
        version == VERSION_SOPORTADA,
        f"{plantilla}: versión {version!r} no soportada (esperada {VERSION_SOPORTADA})",
    )

    slug = str(datos.get("slug") or raiz.name).strip()
    agentes, perfiles = _agentes(datos, raiz)
    grafo = _grafo(datos, {a.name for a in agentes})

    return ProjectPackage(
        slug=slug,
        name=str(datos.get("name") or slug),
        description=str(datos.get("description") or ""),
        use_case_type=str(datos.get("use_case_type") or "custom"),
        root=raiz,
        agents=agentes,
        graph=grafo,
        profiles=perfiles,
        flow_rules=_reglas_de_flujo(datos, {a.name for a in agentes}),
        gate=_compuerta(datos, {a.name for a in agentes}),
        research=_investigacion(datos),
    )


# ── Descubrimiento ──────────────────────────────────────────────────────────

def available_slugs() -> List[str]:
    """Proyectos empaquetados en el filesystem, por orden alfabético."""
    if not PROJECTS_ROOT.is_dir():
        return []
    return sorted(
        d.name for d in PROJECTS_ROOT.iterdir()
        if d.is_dir() and (d / PLANTILLA).is_file()
    )


@lru_cache(maxsize=None)
def load(slug: str) -> ProjectPackage:
    """Carga (y cachea) el proyecto `slug`.

    Se cachea porque la plantilla se lee en cada arranque de pipeline y no
    cambia en caliente; `load.cache_clear()` la recarga cuando haga falta (los
    tests lo usan).
    """
    raiz = PROJECTS_ROOT / slug
    _exigir(raiz.is_dir(), f"No existe el proyecto '{slug}' en {PROJECTS_ROOT}")
    paquete = load_from(raiz)
    logger.info(
        "Proyecto '%s' cargado: %s agente(s), flujo %s",
        paquete.slug, len(paquete.agents), list(paquete.graph.sequence),
    )
    return paquete


def load_all() -> List[ProjectPackage]:
    return [load(slug) for slug in available_slugs()]


def register_all() -> None:
    """Da de alta en el motor los agentes de todos los proyectos empaquetados."""
    for paquete in load_all():
        paquete.register()
