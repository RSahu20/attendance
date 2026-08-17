from datetime import date
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from attendance.domain.attendance import AttendanceStatus
from attendance.domain.security import ClassificationLevel


class RetrievalMode(StrEnum):
    STRUCTURED = "structured"
    DOCUMENT = "document"
    HYBRID = "hybrid"
    UNSUPPORTED = "unsupported"


class StructuredMetric(StrEnum):
    COUNT = "count"
    AVERAGE_PERCENTAGE = "average_percentage"
    TOTAL_HOURS = "total_hours"
    HIGHEST_PERCENTAGE = "highest_percentage"
    LOWEST_PERCENTAGE = "lowest_percentage"
    STATUS_BREAKDOWN = "status_breakdown"


class QueryFilters(BaseModel):
    model_config = ConfigDict(frozen=True)

    date_from: date | None = None
    date_to: date | None = None
    employee_id: str | None = Field(default=None, max_length=255)
    department: str | None = Field(default=None, max_length=255)
    status: AttendanceStatus | None = None


class RetrievalRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    entity_id: UUID
    module: str = Field(default="attendance", min_length=1, max_length=64)
    classification: ClassificationLevel = ClassificationLevel.INTERNAL
    filters: QueryFilters = Field(default_factory=QueryFilters)


class EvidenceItem(BaseModel):
    evidence_id: str
    chunk_id: UUID
    document_version_id: UUID
    content: str
    source_locator: dict[str, Any]
    retrieval_methods: list[str]
    score: float
    extraction_confidence: float
    review_status: str


class RetrievalResponse(BaseModel):
    request_id: UUID
    audit_id: UUID
    retrieval_mode: RetrievalMode
    available: bool
    unavailable_reason: str | None = None
    structured_result: dict[str, Any] | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
