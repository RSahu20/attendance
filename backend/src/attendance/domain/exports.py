from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from attendance.domain.attendance import AttendanceStatus
from attendance.domain.security import ClassificationLevel


class ExportFormat(StrEnum):
    JSON = "json"
    XLSX = "xlsx"
    PDF = "pdf"


class ExportStatus(StrEnum):
    REQUESTED = "requested"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class ExportRequest(BaseModel):
    format: ExportFormat
    dataset: Literal["attendance"] = "attendance"
    entity_id: UUID
    module: str = Field(default="attendance", min_length=1, max_length=64)
    classification: ClassificationLevel = ClassificationLevel.INTERNAL
    date_from: date | None = None
    date_to: date | None = None
    employee_id: str | None = Field(default=None, max_length=255)
    status: AttendanceStatus | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> "ExportRequest":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must not be after date_to")
        return self


class ExportRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    attendance_date: date
    employee_id: str
    employee_name: str | None
    department: str | None
    status: str
    check_in: datetime | None
    check_out: datetime | None
    total_hours: float | None
    attendance_percentage: float | None
    source_file: str
    source_page: int | None
    source_sheet: str | None
    source_row: int | None
    source_record_id: str
    extraction_confidence: float
    review_status: str


class ExportArtifact(BaseModel):
    content: bytes
    media_type: str
    extension: str


class ExportJobResponse(BaseModel):
    export_id: UUID
    status: ExportStatus
    format: ExportFormat
    created_at: datetime
    expires_at: datetime
    record_count: int
    error_code: str | None = None


class ExportMetadata(BaseModel):
    export_id: UUID
    exported_at: datetime
    product_id: UUID
    tenant_id: UUID
    entity_id: UUID
    module: str
    classification: int
    filters: dict[str, Any]
