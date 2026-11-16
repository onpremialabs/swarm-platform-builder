"""Traza de explicabilidad por paso de agente (SPEC-014 / T9.1 / AC1).

`agent_runs` ya registraba **que** un agente corrió y con qué entrada y salida.
Lo que no registraba es **por qué** salió lo que salió: qué fragmentos del RAG se
recuperaron y con qué puntuación, con qué modelo y parámetros se generó, cuántos
tokens costó, y con qué criterio el revisor rechazó un borrador. Sin eso, una
ejecución solo se puede explicar mirando logs de texto con emojis que además
caducan, o los eventos SSE, que son efímeros por definición.

Esta tabla es ese sustrato. La escribe el orquestador al cerrar cada nodo —también
cuando el nodo falla o la ejecución se cancela—, porque una traza que solo existe
cuando todo va bien no sirve para explicar lo que se quiere explicar.

Un paso ≠ un agente: el bucle revisor→redactor hace que el mismo agente aparezca
varias veces, y `step_index` e `iteration` los distinguen.
"""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text,
    UUID as SA_UUID,
)

from app.core.database import Base


class AgentRunStepModel(Base):
    """Un paso de agente dentro de una ejecución del pipeline."""

    __tablename__ = "agent_run_steps"
    __table_args__ = (
        # La consulta que sirve el panel «Por qué este resultado» (T9.2) es
        # siempre «los pasos de este artículo, en orden».
        Index("ix_agent_run_steps_article_step", "article_id", "step_index"),
    )

    id = Column(SA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    # `SET NULL` y no `CASCADE`: si se purga un `agent_run` por retención, la
    # traza del paso sigue explicando lo que pasó hasta que le toque a ella.
    run_id = Column(
        SA_UUID(as_uuid=True), ForeignKey("agent_runs.run_id", ondelete="SET NULL"), index=True
    )
    article_id = Column(
        SA_UUID(as_uuid=True), ForeignKey("articles.id", ondelete="CASCADE"), index=True
    )
    project_id = Column(SA_UUID(as_uuid=True), index=True)

    #: Identificador de correlación de T5.1, para cruzar la traza con los logs.
    correlation_id = Column(String(64), index=True)

    agent_name = Column(String(64), nullable=False)
    #: Posición en la ejecución (0, 1, 2…) e iteración del bucle de revisión.
    step_index = Column(Integer, default=0, nullable=False)
    iteration = Column(Integer, default=0, nullable=False)

    status = Column(String(16), default="completed", nullable=False, index=True)
    error_message = Column(Text)

    model = Column(String(128))
    #: temperature, num_ctx, y lo que el perfil aporte. JSON porque cada
    #: proveedor tiene los suyos y fijarlos en columnas envejecería mal.
    params = Column(JSON, default=dict, nullable=False)

    #: Resumen de la entrada, no la entrada entera: el prompt completo puede
    #: llevar el borrador y las fuentes, y la traza no es un segundo almacén del
    #: artículo. Ver `docs/governance/data-retention.md`.
    input_digest = Column(Text)
    output_text = Column(Text)

    #: [{doc_id, chunk_ids, score, title, authors, collection}] — lo que el paso
    #: recuperó de verdad, no lo que citó el texto final.
    rag_sources = Column(JSON, default=list, nullable=False)

    tokens_in = Column(Integer, default=0, nullable=False)
    tokens_out = Column(Integer, default=0, nullable=False)
    latency_ms = Column(Float, default=0.0, nullable=False)

    #: {score, coherent, hitl_outcome} cuando el paso decide algo.
    decision = Column(JSON)
    rationale = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    #: Cadena de integridad (SPEC-029 / T17.2 / AC4). `content_hash` es
    #: `sha256(canónico(paso) || prev_hash)`, y `prev_hash` el del paso anterior
    #: de la **misma** ejecución; el primero ancla en un valor conocido.
    #: Anulables porque las filas escritas antes de T17.2 no los tienen: la
    #: verificación las cuenta como «sin cadena», que no es lo mismo que
    #: «manipuladas».
    content_hash = Column(String(64))
    prev_hash = Column(String(64))
    #: Versión de la serialización canónica con la que se calculó el hash. Va en
    #: la fila para que un cambio futuro de formato no invalide lo ya escrito.
    hash_version = Column(Integer)


class AgentRunStepResponse(BaseModel):
    """Un paso de la traza, tal y como lo devuelve la API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID | None = None
    article_id: UUID | None = None
    correlation_id: str | None = None
    agent_name: str
    step_index: int
    iteration: int
    status: str
    error_message: str | None = None
    model: str | None = None
    params: dict = {}
    input_digest: str | None = None
    output_text: str | None = None
    rag_sources: list = []
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    decision: dict | None = None
    rationale: str | None = None
    created_at: datetime
    content_hash: str | None = None
    prev_hash: str | None = None
    hash_version: int | None = None


class ExplainSource(BaseModel):
    """Una fuente del RAG, agregada a través de todos los pasos que la usaron.

    La traza guarda las fuentes **por paso**, que es lo correcto para explicar un
    paso concreto. Pero la pregunta que trae a alguien al panel suele ser la otra:
    «¿en qué documentos se apoya este artículo?». Reconstruirlo en el cliente
    obliga a recorrer los pasos y desduplicar, y cada cliente lo haría distinto.
    """

    doc_id: str
    title: str | None = None
    authors: str | None = None
    collection: str | None = None
    #: El **mejor** score con el que se recuperó en cualquier paso.
    score: float = 0.0
    chunk_ids: list = []
    #: Agentes que la recuperaron, en orden de aparición.
    used_by: list[str] = []


class ExplainTotals(BaseModel):
    """Lo que costó la ejecución. Es la mitad de «por qué este resultado»: la
    otra mitad son las fuentes y las decisiones."""

    steps: int = 0
    agents: list[str] = []
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    #: Vueltas del bucle revisor→redactor (0 = el borrador se aprobó a la primera).
    loops: int = 0
    failed_steps: int = 0


class ArticleExplainResponse(BaseModel):
    """Traza de explicabilidad de un artículo (SPEC-014 / T9.2 / AC2)."""

    article_id: UUID
    title: str
    #: Cuántas ejecuciones del pipeline tiene el artículo. Más de una significa
    #: que lo que se está leyendo lo produjo la última, y el panel lo dice.
    executions: int = 0
    #: Qué se está devolviendo: `last` (la ejecución que produjo el texto actual)
    #: o `all` (todas). Va en la respuesta y no solo en la petición para que un
    #: informe guardado siga diciendo de qué habla.
    scope: str = "last"
    #: `False` cuando el artículo existe pero no hay traza: una ejecución anterior
    #: a T9.1, o purgada por retención. La interfaz necesita distinguirlo de «este
    #: artículo no se ha ejecutado nunca», que es otra cosa y se arregla de otra
    #: manera.
    available: bool = False
    steps: list[AgentRunStepResponse] = []
    sources: list[ExplainSource] = []
    totals: ExplainTotals = ExplainTotals()
