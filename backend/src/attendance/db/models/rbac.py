from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from attendance.db.base import Base


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str] = mapped_column(String(500))


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("product_id", "tenant_id", "id", name="uq_roles_scope_id"),
        UniqueConstraint("product_id", "tenant_id", "name", name="uq_roles_scope_name"),
        ForeignKeyConstraint(
            ["product_id", "tenant_id"],
            ["tenants.product_id", "tenants.id"],
            name="fk_roles_scope_tenants",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )


class UserRoleAssignment(Base):
    __tablename__ = "user_role_assignments"
    __table_args__ = (
        CheckConstraint(
            "classification_ceiling BETWEEN 0 AND 3",
            name="classification_ceiling_range",
        ),
        ForeignKeyConstraint(
            ["role_id", "product_id", "tenant_id"],
            ["roles.id", "roles.product_id", "roles.tenant_id"],
            name="fk_assignments_role_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["product_id", "tenant_id", "entity_id"],
            ["entities.product_id", "entities.tenant_id", "entities.id"],
            name="fk_assignments_entity_scope",
            ondelete="CASCADE",
        ),
        Index("ix_assignments_user_scope", "user_id", "product_id", "tenant_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    module: Mapped[str | None] = mapped_column(String(64))
    classification_ceiling: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
