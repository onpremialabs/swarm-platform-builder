"""Agent run ORM model and DTOs."""
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, String, DateTime, UUID as SA_UUID, ForeignKey, Text, Integer, JSON

from app.core.database import Base


class AgentRunModel(Base):
    """Agent execution run tracking model."""
    __tablename__ = "agent_runs"

    run_id = Column(SA_UUID(as_uuid=True), primary_key=True, default=uuid4)
    agent_name = Column(String(64), nullable=False)
    article_id = Column(SA_UUID(as_uuid=True), ForeignKey("articles.id", ondelete="SET NULL"), index=True)
    author_id = Column(SA_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    status = Column(String(16), default="running", nullable=False, index=True)
    input_payload = Column(JSON, default=dict, nullable=False)
    output_payload = Column(JSON)
    tokens_used = Column(Integer, default=0, nullable=False)
    error_message = Column(Text)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime)


class AgentRunRequest(BaseModel):
    """Request for running the agent pipeline."""
    flow_sequence: list[str] = Field(..., min_length=1)
    agent_settings: dict[str, dict] = Field(default={})
    keywords: list[str] = Field(default=[])
    context_description: str = Field(default="")
    article_outline: str = Field(default="")

    # Parámetros de esta ejecución (SPEC-030 / T18.3, T18.5 / AC3, AC6, AC7).
    #: Notas libres. El tope de verdad lo pone `sanitize_notes`, que además dice
    #: si recortó; aquí se acota para rechazar un cuerpo absurdo antes de leerlo.
    swarm_notes: str = Field(default="", max_length=10_000)
    #: Documento de referencia acotado a este paper (T18.1 / AC1).
    reference_doc_id: str | None = Field(default=None)
    #: Cómo se aprende el formato. Se valida contra `FORMAT_MODES`, que declara
    #: cuál está disponible y por qué (AC6).
    format_mode: str = Field(default="rag")


class AgentRunDetailResponse(BaseModel):
    """Detailed response of a single agent run step."""
    model_config = ConfigDict(from_attributes=True)

    run_id: UUID
    agent_name: str
    article_id: UUID | None
    author_id: UUID | None
    status: str
    input_payload: dict | None = None
    output_payload: dict | None = None
    tokens_used: int
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class AgentRunListResponse(BaseModel):
    """Response containing a list of agent runs."""
    runs: list[AgentRunDetailResponse]
