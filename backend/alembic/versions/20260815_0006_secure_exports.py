"""Add protected export jobs and export permission.

Revision ID: 20260815_0006
Revises: 20260815_0005
Create Date: 2026-08-15
"""

from alembic import op

revision: str = "20260815_0006"
down_revision: str | None = "20260815_0005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO permissions (id, code, description)
        VALUES (gen_random_uuid(), 'attendance:export', 'Export authorized attendance records')
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        CREATE TABLE export_jobs (
            id uuid PRIMARY KEY,
            request_id uuid NOT NULL,
            product_id uuid NOT NULL,
            tenant_id uuid NOT NULL,
            entity_id uuid NOT NULL,
            module varchar(64) NOT NULL,
            classification integer NOT NULL,
            requested_by_user_id uuid NOT NULL,
            format varchar(16) NOT NULL,
            dataset varchar(32) NOT NULL DEFAULT 'attendance',
            filters jsonb NOT NULL DEFAULT '{}'::jsonb,
            status varchar(32) NOT NULL DEFAULT 'requested',
            storage_key varchar(1024),
            filename varchar(255),
            media_type varchar(255),
            record_count integer NOT NULL DEFAULT 0,
            byte_size bigint NOT NULL DEFAULT 0,
            failure_code varchar(128),
            expires_at timestamptz NOT NULL,
            completed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_export_jobs_request_id UNIQUE (request_id),
            CONSTRAINT ck_export_jobs_classification_range
                CHECK (classification BETWEEN 0 AND 3),
            CONSTRAINT ck_export_jobs_valid_format
                CHECK (format IN ('json', 'xlsx', 'pdf')),
            CONSTRAINT ck_export_jobs_valid_status
                CHECK (status IN ('requested', 'completed', 'failed', 'expired')),
            CONSTRAINT ck_export_jobs_nonnegative_record_count CHECK (record_count >= 0),
            CONSTRAINT ck_export_jobs_nonnegative_byte_size CHECK (byte_size >= 0),
            CONSTRAINT fk_export_jobs_entity_scope FOREIGN KEY (
                product_id, tenant_id, entity_id
            ) REFERENCES entities (product_id, tenant_id, id) ON DELETE CASCADE,
            CONSTRAINT fk_export_jobs_requested_by_user_id_users FOREIGN KEY (
                requested_by_user_id
            ) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_export_jobs_scope_created ON export_jobs "
        "(product_id, tenant_id, entity_id, module, created_at)"
    )
    op.execute(
        "CREATE INDEX ix_export_jobs_requester ON export_jobs (requested_by_user_id, created_at)"
    )
    op.execute("CREATE INDEX ix_export_jobs_expiry ON export_jobs (expires_at)")
    op.execute("ALTER TABLE export_jobs ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY export_jobs_scope_select ON export_jobs
        FOR SELECT USING (
            app_scope_allows(
                product_id, tenant_id, entity_id, module, classification, 'attendance:export'
            )
        )
        """
    )
    op.execute(
        """
        CREATE POLICY export_jobs_scope_insert ON export_jobs
        FOR INSERT WITH CHECK (
            app_scope_allows(
                product_id, tenant_id, entity_id, module, classification, 'attendance:export'
            )
        )
        """
    )
    op.execute(
        """
        CREATE POLICY export_jobs_scope_update ON export_jobs
        FOR UPDATE
        USING (
            app_scope_allows(
                product_id, tenant_id, entity_id, module, classification, 'attendance:export'
            )
        )
        WITH CHECK (
            app_scope_allows(
                product_id, tenant_id, entity_id, module, classification, 'attendance:export'
            )
        )
        """
    )
    op.execute(
        """
        CREATE POLICY export_jobs_scope_delete ON export_jobs
        FOR DELETE USING (
            app_scope_allows(
                product_id, tenant_id, entity_id, module, classification, 'attendance:export'
            )
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE export_jobs")
    op.execute("DELETE FROM permissions WHERE code = 'attendance:export'")
