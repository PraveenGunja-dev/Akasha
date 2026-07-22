"""Typed contracts for the Akasha chatbot runtime."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, validator


IntentType = Literal["factual", "analytical", "advisory", "document", "unsupported", "deep_analysis"]
ChatMode = Literal["auto", "fast", "analysis"]
RunStatus = Literal["success", "partial", "clarification", "error"]
ToolStatus = Literal["success", "partial", "not_found", "unauthorized", "error"]


class ChatRequestContract(BaseModel):
    """Versioned HTTP request contract accepted by the chatbot router."""

    model_config = {"populate_by_name": True, "extra": "forbid"}

    contract_version: Literal["chat.request.v1"] = "chat.request.v1"
    message: str = Field(..., min_length=1, max_length=12000)
    history: list[dict[str, Any]] = Field(default_factory=list)
    project_id: str | None = Field(default=None, alias="projectId")
    session_id: str | None = Field(default=None, alias="sessionId")
    is_deep_analysis: bool = Field(default=False, alias="isDeepAnalysis")
    image_data: str | None = Field(default=None, alias="imageData")
    mode: ChatMode = "auto"
    client_version: str | None = None

    @validator("message")
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value


class ChatSseEventContract(BaseModel):
    """Version marker for the active server-sent event stream."""

    contract_version: Literal["chat.sse.v1"] = "chat.sse.v1"
    type: str


class UserScope(BaseModel):
    user_id: str | None = None
    username: str | None = None
    role: str = "anonymous"
    project_ids: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    can_access_portfolio: bool = False
    is_authenticated: bool = False


class EvidenceItem(BaseModel):
    source_system: str
    source_type: str
    record_ids: list[str] = Field(default_factory=list)
    project_id: str | None = None
    as_of: str | None = None
    retrieved_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    calculation: str | None = None
    calculation_version: str | None = None


class SourceFreshness(BaseModel):
    as_of: str | None = None
    status: Literal["fresh", "stale", "missing"] = "missing"


class ToolResultEnvelope(BaseModel):
    status: ToolStatus
    data: Any = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class ProjectCandidate(BaseModel):
    project_id: str
    project_name: str
    p6_name: str | None = None
    spv_name: str | None = None
    score: float
    match_type: str


class ProjectResolution(BaseModel):
    status: Literal["resolved", "ambiguous", "not_found", "not_project_specific"]
    project_ids: list[str] = Field(default_factory=list)
    candidates: list[ProjectCandidate] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low", "insufficient"] = "insufficient"
    question: str | None = None


class ChatCompletionMetadata(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    conversation_id: str
    message_id: int | None = None
    mode: Literal["fast", "analysis"]
    intent: IntentType
    project_ids: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    freshness: dict[str, SourceFreshness] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    latency_ms: int = 0
    status: RunStatus


class ChatResponse(BaseModel):
    content: str
    intent_type: IntentType
    project_ids: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    freshness: dict[str, SourceFreshness] = Field(default_factory=dict)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    sources_used: list[str] = Field(default_factory=list)
    latency_ms: int
    status: RunStatus = "success"
    clarification: str | None = None
    run_id: str = Field(default_factory=lambda: str(uuid4()))

    @property
    def data_as_of(self) -> str | None:
        timestamps = [
            fresh.as_of
            for fresh in self.freshness.values()
            if fresh.as_of and fresh.status != "missing"
        ]
        return min(timestamps) if timestamps else None
