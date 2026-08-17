from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from attendance.db.base import Base


class ExportJob(Base):
    __tablename__ = "export_jobs"
    __table_args__ = (
        CheckConstraint("classification BETWEEN 0 AND 3", name="classification_range"),
        CheckConstraint("format IN ('json', 'xlsx', 'pdf')", name="valid_format"),
        CheckConstraint(
            "status IN ('requested', 'completed', 'failed', 'expired')",
            name="valid_status",
        ),
        CheckConstraint("record_count >= 0", name="nonnegative_record_count"),
        CheckConstraint("byte_size >= 0", name="nonnegative_byte_size"),
        ForeignKeyConstraint(
            ["product_id", "tenant_id", "entity_id"],
            ["entities.product_id", "entities.tenant_id", "entities.id"],
            name="fk_export_jobs_entity_scope",
            ondelete="CASCADE",
        ),
        Index(
            "ix_export_jobs_scope_created",
            "product_id",
            "tenant_id",
            "entity_id",
            "module",
            "created_at",
        ),
        Index("ix_export_jobs_requester", "requested_by_user_id", "created_at"),
        Index("ix_export_jobs_expiry", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, unique=True, default=uuid4
    )
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    classification: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    dataset: Mapped[str] = mapped_column(String(32), nullable=False, default="attendance")
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="requested")
    storage_key: Mapped[str | None] = mapped_column(String(1024))
    filename: Mapped[str | None] = mapped_column(String(255))
    media_type: Mapped[str | None] = mapped_column(String(255))
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    failure_code: Mapped[str | None] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
