from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
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


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint("classification BETWEEN 0 AND 3", name="classification_range"),
        ForeignKeyConstraint(
            ["product_id", "tenant_id"],
            ["tenants.product_id", "tenants.id"],
            name="fk_audit_events_scope_tenants",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["product_id", "tenant_id", "entity_id"],
            ["entities.product_id", "entities.tenant_id", "entities.id"],
            name="fk_audit_events_entity_scope",
            ondelete="RESTRICT",
        ),
        Index("ix_audit_events_scope_created", "product_id", "tenant_id", "created_at"),
        Index("ix_audit_events_request_id", "request_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    module: Mapped[str | None] = mapped_column(String(64))
    classification: Mapped[int] = mapped_column(Integer, nullable=False)
    role_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255))
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
