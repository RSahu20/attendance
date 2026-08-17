from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from attendance.domain.retrieval import RetrievalMode


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    UNAVAILABLE = "unavailable"


class ConfidenceBand(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ProviderCitation(BaseModel):
    evidence_id: str
    claim: str = Field(min_length=1, max_length=4000)


class ProviderOutput(BaseModel):
    answer: str = Field(min_length=1, max_length=12000)
    citations: list[ProviderCitation] = Field(default_factory=list, max_length=32)


class GenerationContextItem(BaseModel):
    evidence_id: str
    chunk_id: UUID
    document_version_id: UUID
    content: str
    source_locator: dict[str, Any]
    retrieval_methods: list[str]
    retrieval_score: float
    extraction_confidence: float
    review_status: str
    injection_detected: bool = False


class GenerationContext(BaseModel):
    structured_result: dict[str, Any] | None = None
    evidence: list[GenerationContextItem] = Field(default_factory=list)


class LLMRequest(BaseModel):
    question: str
    context: GenerationContext
    correction_errors: list[str] = Field(default_factory=list)


class ValidatedCitation(BaseModel):
    evidence_id: str
    chunk_id: UUID
    document_version_id: UUID
    source_locator: dict[str, Any]
    claim: str
    validated: bool = True


class ConfidenceResult(BaseModel):
    score: float = Field(ge=0, le=1)
    band: ConfidenceBand


class AnswerResponse(BaseModel):
    answer: str
    tenant_context: dict[str, UUID]
    entity_context: dict[str, list[UUID]]
    role_context: dict[str, list[UUID]]
    citations: list[ValidatedCitation] = Field(default_factory=list)
    confidence: ConfidenceResult
    retrieval_mode: RetrievalMode
    request_id: UUID
    audit_id: UUID
    status: AnswerStatus
    unavailable_reason: str | None = None
