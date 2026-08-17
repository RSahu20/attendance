"""Add tenant, RBAC, classification, RLS-context, and audit foundations.

Revision ID: 20260815_0002
Revises: 20260815_0001
Create Date: 2026-08-15
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260815_0002"
down_revision: str | None = "20260815_0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
        sa.UniqueConstraint("code", name="uq_products_code"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("subject", name="uq_users_subject"),
    )
    op.create_table(
        "permissions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_permissions"),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )
    op.create_table(
        "tenants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_tenants_product_id_products",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tenants"),
        sa.UniqueConstraint("product_id", "code", name="uq_tenants_product_code"),
        sa.UniqueConstraint("product_id", "id", name="uq_tenants_product_id_id"),
    )
    op.create_table(
        "entities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["product_id", "tenant_id"],
            ["tenants.product_id", "tenants.id"],
            name="fk_entities_scope_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id", "tenant_id", "parent_id"],
            ["entities.product_id", "entities.tenant_id", "entities.id"],
            name="fk_entities_parent_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_entities"),
        sa.UniqueConstraint("product_id", "tenant_id", "code", name="uq_entities_scope_code"),
        sa.UniqueConstraint("product_id", "tenant_id", "id", name="uq_entities_scope_id"),
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["product_id", "tenant_id"],
            ["tenants.product_id", "tenants.id"],
            name="fk_roles_scope_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
        sa.UniqueConstraint("product_id", "tenant_id", "id", name="uq_roles_scope_id"),
        sa.UniqueConstraint("product_id", "tenant_id", "name", name="uq_roles_scope_name"),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column("permission_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["permissions.id"],
            name="fk_role_permissions_permission_id_permissions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name="fk_role_permissions_role_id_roles",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name="pk_role_permissions"),
    )
    op.create_table(
        "user_role_assignments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column("module", sa.String(length=64), nullable=True),
        sa.Column("classification_ceiling", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "classification_ceiling BETWEEN 0 AND 3",
            name="ck_user_role_assignments_classification_ceiling_range",
        ),
        sa.ForeignKeyConstraint(
            ["product_id", "tenant_id", "entity_id"],
            ["entities.product_id", "entities.tenant_id", "entities.id"],
            name="fk_assignments_entity_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id", "product_id", "tenant_id"],
            ["roles.id", "roles.product_id", "roles.tenant_id"],
            name="fk_assignments_role_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_role_assignments_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_role_assignments"),
    )
    op.create_index(
        "ix_assignments_user_scope",
        "user_role_assignments",
        ["user_id", "product_id", "tenant_id"],
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column("module", sa.String(length=64), nullable=True),
        sa.Column("classification", sa.Integer(), nullable=False),
        sa.Column("role_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=128), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "classification BETWEEN 0 AND 3",
            name="ck_audit_events_classification_range",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_audit_events_actor_user_id_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["product_id", "tenant_id", "entity_id"],
            ["entities.product_id", "entities.tenant_id", "entities.id"],
            name="fk_audit_events_entity_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id", "tenant_id"],
            ["tenants.product_id", "tenants.id"],
            name="fk_audit_events_scope_tenants",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"], unique=False)
    op.create_index(
        "ix_audit_events_scope_created",
        "audit_events",
        ["product_id", "tenant_id", "created_at"],
        unique=False,
    )

    op.execute(
        """
        CREATE FUNCTION app_scope_allows(
            row_product_id uuid,
            row_tenant_id uuid,
            row_entity_id uuid,
            row_module text,
            row_classification integer,
            required_permission text
        ) RETURNS boolean
        LANGUAGE sql
        STABLE
        PARALLEL SAFE
        AS $$
            SELECT
                NULLIF(current_setting('app.product_id', true), '')::uuid = row_product_id
                AND NULLIF(current_setting('app.tenant_id', true), '')::uuid = row_tenant_id
                AND EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements(
                        COALESCE(
                            NULLIF(current_setting('app.authorization_grants', true), '')::jsonb,
                            '[]'::jsonb
                        )
                    ) AS scope_grant
                    WHERE (
                        scope_grant->>'entity_id' IS NULL
                        OR (scope_grant->>'entity_id')::uuid = row_entity_id
                    )
                      AND (
                        scope_grant->>'module' IS NULL
                        OR scope_grant->>'module' = row_module
                      )
                      AND (scope_grant->>'classification_ceiling')::integer >= row_classification
                      AND scope_grant->'permissions' ? required_permission
                );
        $$;
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_audit_event_mutation() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'audit events are append-only';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_append_only
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION reject_audit_event_mutation();
        """
    )
    op.execute("ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY audit_events_scope_select ON audit_events
        FOR SELECT USING (
            app_scope_allows(
                product_id, tenant_id, entity_id, module, classification, 'audit:read'
            )
        );
        """
    )
    op.execute(
        """
        CREATE POLICY audit_events_scope_insert ON audit_events
        FOR INSERT WITH CHECK (
            app_scope_allows(
                product_id, tenant_id, entity_id, module, classification, 'audit:write'
            )
        );
        """
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.execute("DROP FUNCTION reject_audit_event_mutation()")
    op.execute("DROP FUNCTION app_scope_allows(uuid, uuid, uuid, text, integer, text)")
    op.drop_index("ix_assignments_user_scope", table_name="user_role_assignments")
    op.drop_table("user_role_assignments")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("entities")
    op.drop_table("tenants")
    op.drop_table("permissions")
    op.drop_table("users")
    op.drop_table("products")
