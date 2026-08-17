from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from attendance.domain.security import ClassificationLevel


class AttendanceStatus(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    EXCUSED = "excused"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class ReviewStatus(StrEnum):
    ACCEPTED = "accepted"
    REVIEW_REQUIRED = "review_required"
    REJECTED = "rejected"


class ExtractionMethod(StrEnum):
    NATIVE = "native"
    CSV = "csv"
    XLSX = "xlsx"
    DOCX = "docx"
    PDF_TEXT = "pdf_text"
    OCR = "ocr"
    MANUAL = "manual"


class CanonicalAttendanceRecord(BaseModel):
    """Format-neutral attendance fact produced by future normalization code."""

    model_config = ConfigDict(frozen=True)

    product_id: UUID
    tenant_id: UUID
    entity_id: UUID
    module: str = Field(min_length=1, max_length=64)
    classification: ClassificationLevel

    subject_external_id: str = Field(min_length=1, max_length=255)
    subject_display_name: str | None = Field(default=None, max_length=255)
    attendance_date: date
    session_external_id: str | None = Field(default=None, max_length=255)
    session_name: str | None = Field(default=None, max_length=255)
    course_or_group: str | None = Field(default=None, max_length=255)
    status: AttendanceStatus

    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    check_in: datetime | None = None
    check_out: datetime | None = None
    scheduled_minutes: int | None = Field(default=None, ge=0)
    attended_minutes: int | None = Field(default=None, ge=0)
    attendance_percentage: Decimal | None = Field(default=None, ge=0, le=100)
    late_minutes: int | None = Field(default=None, ge=0)

    source_document_id: UUID
    source_version_id: UUID
    source_unit_id: UUID
    source_record_key: str = Field(min_length=1, max_length=255)
    raw_row_metadata: dict[str, Any] = Field(default_factory=dict)

    extraction_method: ExtractionMethod
    extraction_confidence: Decimal = Field(ge=0, le=1)
    review_status: ReviewStatus
    normalization_warnings: list[str] = Field(default_factory=list)
    recorded_at: datetime | None = None

    @model_validator(mode="after")
    def validate_time_ranges(self) -> "CanonicalAttendanceRecord":
        if (
            self.scheduled_start
            and self.scheduled_end
            and self.scheduled_end < self.scheduled_start
        ):
            raise ValueError("scheduled_end cannot precede scheduled_start")
        if self.check_in and self.check_out and self.check_out < self.check_in:
            raise ValueError("check_out cannot precede check_in")
        return self
