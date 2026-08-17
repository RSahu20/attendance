from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from attendance.db.base import Base


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        CheckConstraint("classification BETWEEN 0 AND 3", name="classification_range"),
        CheckConstraint(
            "status IN ('present', 'absent', 'late', 'excused', 'partial', 'unknown')",
            name="valid_status",
        ),
        CheckConstraint(
            "review_status IN ('accepted', 'review_required', 'rejected')",
            name="valid_review_status",
        ),
        CheckConstraint(
            "extraction_method IN ('native', 'csv', 'xlsx', 'docx', 'pdf_text', 'ocr', 'manual')",
            name="valid_extraction_method",
        ),
        CheckConstraint("extraction_confidence BETWEEN 0 AND 1", name="confidence_range"),
        CheckConstraint(
            "attendance_percentage IS NULL OR attendance_percentage BETWEEN 0 AND 100",
            name="percentage_range",
        ),
        CheckConstraint(
            "scheduled_minutes IS NULL OR scheduled_minutes >= 0",
            name="nonnegative_scheduled_minutes",
        ),
        CheckConstraint(
            "attended_minutes IS NULL OR attended_minutes >= 0",
            name="nonnegative_attended_minutes",
        ),
        CheckConstraint(
            "late_minutes IS NULL OR late_minutes >= 0",
            name="nonnegative_late_minutes",
        ),
        CheckConstraint(
            "scheduled_start IS NULL OR scheduled_end IS NULL OR scheduled_end >= scheduled_start",
            name="scheduled_time_order",
        ),
        CheckConstraint(
            "check_in IS NULL OR check_out IS NULL OR check_out >= check_in",
            name="check_time_order",
        ),
        ForeignKeyConstraint(
            [
                "product_id",
                "tenant_id",
                "entity_id",
                "module",
                "classification",
                "source_document_id",
            ],
            [
                "documents.product_id",
                "documents.tenant_id",
                "documents.entity_id",
                "documents.module",
                "documents.classification",
                "documents.id",
            ],
            name="fk_attendance_records_document_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            [
                "product_id",
                "tenant_id",
                "entity_id",
                "module",
                "classification",
                "source_version_id",
            ],
            [
                "document_versions.product_id",
                "document_versions.tenant_id",
                "document_versions.entity_id",
                "document_versions.module",
                "document_versions.classification",
                "document_versions.id",
            ],
            name="fk_attendance_records_version_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            [
                "product_id",
                "tenant_id",
                "entity_id",
                "module",
                "classification",
                "source_unit_id",
            ],
            [
                "extracted_units.product_id",
                "extracted_units.tenant_id",
                "extracted_units.entity_id",
                "extracted_units.module",
                "extracted_units.classification",
                "extracted_units.id",
            ],
            name="fk_attendance_records_unit_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "source_version_id",
            "source_record_key",
            name="uq_attendance_records_source_key",
        ),
        Index(
            "ix_attendance_records_scope_date",
            "product_id",
            "tenant_id",
            "entity_id",
            "module",
            "attendance_date",
        ),
        Index("ix_attendance_records_subject_date", "subject_external_id", "attendance_date"),
        Index("ix_attendance_records_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    classification: Mapped[int] = mapped_column(Integer, nullable=False)

    subject_external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_display_name: Mapped[str | None] = mapped_column(String(255))
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False)
    session_external_id: Mapped[str | None] = mapped_column(String(255))
    session_name: Mapped[str | None] = mapped_column(String(255))
    course_or_group: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    scheduled_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_minutes: Mapped[int | None] = mapped_column(Integer)
    attended_minutes: Mapped[int | None] = mapped_column(Integer)
    attendance_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    late_minutes: Mapped[int | None] = mapped_column(Integer)

    source_document_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_unit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_record_key: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_row_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    extraction_method: Mapped[str] = mapped_column(String(32), nullable=False)
    extraction_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False)
    normalization_warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
