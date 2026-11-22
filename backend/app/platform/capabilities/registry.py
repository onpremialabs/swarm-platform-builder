"""Registro tipado de capacidades del motor (SPEC-013 AC3, ADR-0005).

Declara las capacidades genéricas de la plataforma (rag/search/scrape/format/
publish/llm) como objetos tipados con un *entrypoint* perezoso ("módulo:atributo")
que se resuelve por import absoluto solo cuando se necesita. Esto permite listar
las capacidades sin arrastrar dependencias pesadas (httpx, pypdf, openai…).

Alcance de T8.2: el registro describe y resuelve las capacidades existentes; el
re-cableado del orquestador para consumirlas es T8.3 (AC5/AC8). Las capacidades
`format` y `publish` referencian por ahora los adapters de AlejandrIA
(`paper_layout`, `publicador`) que se generalizarán en T8.3/T8.4.

La capacidad `scrape` se declara **sin proveedor activo** (`available=False`):
el antiguo `adapters/scraper.py` se eliminó como código muerto (commit
``71e3923``; SPEC-002 quedó Superseded). El tipo se mantiene en el registro
para que el contrato de capacidades sea estable cuando exista un proveedor.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from importlib import import_module
from typing import Any, List


class CapabilityKind(str, Enum):
    """Tipos de capacidad soportados por el motor."""

    RAG = "rag"
    SEARCH = "search"
    SCRAPE = "scrape"
    FORMAT = "format"
    PUBLISH = "publish"
    LLM = "llm"
    LITERATURE = "literature"


class CapabilityNotAvailable(LookupError):
    """La capacidad existe en el registro pero no tiene proveedor activo."""


@dataclass(frozen=True)
class Capability:
    """Descriptor tipado de una capacidad del motor.

    Attributes:
        kind: Tipo de la capacidad (uno de :class:`CapabilityKind`).
        name: Nombre único en el registro (clave de :func:`get`).
        description: Qué hace y quién la provee.
        entrypoint: Referencia perezosa ``"paquete.modulo:atributo"`` a la
            implementación, o ``None`` si no hay proveedor activo.
        available: ``False`` cuando la capacidad se declara como tipo pero no
            tiene proveedor (p. ej. ``scrape``).
    """

    kind: CapabilityKind
    name: str
    description: str
    entrypoint: str | None = None
    available: bool = True

    def resolve(self) -> Any:
        """Importa y devuelve el objeto implementación de la capacidad.

        Raises:
            CapabilityNotAvailable: si la capacidad no tiene proveedor activo.
        """
        if not self.available or not self.entrypoint:
            raise CapabilityNotAvailable(
                f"La capacidad '{self.name}' ({self.kind.value}) no tiene proveedor activo"
            )
        module_path, _, attr = self.entrypoint.partition(":")
        return getattr(import_module(module_path), attr)


_REGISTRY: dict[str, Capability] = {}


def register(capability: Capability) -> Capability:
    """Registra (o reemplaza) una capacidad por su nombre y la devuelve."""
    _REGISTRY[capability.name] = capability
    return capability


def get(name: str) -> Capability:
    """Devuelve la capacidad registrada bajo ``name`` (KeyError si no existe)."""
    return _REGISTRY[name]


def list_capabilities() -> List[Capability]:
    """Lista todas las capacidades registradas, en orden de registro."""
    return list(_REGISTRY.values())


def _register_builtins() -> None:
    """Capacidades de serie del motor, apuntando a la infraestructura real."""
    register(Capability(
        kind=CapabilityKind.RAG,
        name="rag",
        description=(
            "Recuperación aumentada: búsqueda semántica sobre los documentos "
            "del agente y la biblioteca compartida (Qdrant o backend local)."
        ),
        entrypoint="app.platform.capabilities.rag:semantic_search_context",
    ))
    register(Capability(
        kind=CapabilityKind.RAG,
        name="rag_results",
        description=(
            "La misma búsqueda, devolviendo resultados con metadatos (doc_id, "
            "título, autores) en vez de un bloque de texto: es lo que necesita "
            "un agente que construye citas."
        ),
        entrypoint="app.platform.capabilities.rag:semantic_search_results",
    ))
    register(Capability(
        kind=CapabilityKind.SEARCH,
        name="search",
        description="Búsqueda web (DuckDuckGo) con URLs de fuente, vía tool-calling.",
        entrypoint="app.platform.capabilities.tools:ddg_search_with_urls",
    ))
    register(Capability(
        kind=CapabilityKind.SCRAPE,
        name="scrape",
        description=(
            "Extracción de contenido web. Sin proveedor activo: scraper.py se "
            "eliminó como código muerto (SPEC-002 Superseded, commit 71e3923)."
        ),
        entrypoint=None,
        available=False,
    ))
    register(Capability(
        kind=CapabilityKind.FORMAT,
        name="format",
        description=(
            "Maquetación de artículos científicos a HTML (paper_layout). "
            "Referencia al adapter actual; se generaliza en T8.3."
        ),
        entrypoint="app.modules.agents.adapters.paper_layout:build_paper_html",
    ))
    register(Capability(
        kind=CapabilityKind.PUBLISH,
        name="publish",
        description=(
            "Publicación del artículo final (paso publicador del pipeline). "
            "Referencia al adapter actual; se generaliza en T8.3."
        ),
        entrypoint="app.modules.agents.adapters.publicador:run_publicador",
    ))
    register(Capability(
        kind=CapabilityKind.LLM,
        name="llm",
        description="Generación LLM vía el dispatcher único (Anthropic/Ollama/OpenAI).",
        entrypoint="app.platform.llm:call_llm",
    ))
    register(Capability(
        kind=CapabilityKind.LLM,
        name="llm_stream",
        description=(
            "La misma generación, en streaming token a token: es lo que permite "
            "que la redacción se vea escribirse en la interfaz."
        ),
        entrypoint="app.platform.llm:call_llm_stream",
    ))
    register(Capability(
        kind=CapabilityKind.LITERATURE,
        name="literature",
        description=(
            "Descubrimiento de literatura: consulta OpenAlex, Crossref, Semantic Scholar, "
            "arXiv y PubMed (las de `research.sources`) por safe_get con "
            'quien="literature_discovery" y devuelve candidatos normalizados **sin verificar** '
            "(SPEC-034)."
        ),
        entrypoint="app.platform.capabilities.literature:search_literature",
    ))


_register_builtins()
