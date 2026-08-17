"""Add ingestion progress and logical-document idempotency constraints.

Revision ID: 20260815_0004
Revises: 20260815_0003
Create Date: 2026-08-15
"""

from alembic import op

revision: str = "20260815_0004"
down_revision: str | None = "20260815_0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE documents ADD CONSTRAINT uq_documents_logical_scope_name "
        "UNIQUE (product_id, tenant_id, entity_id, module, classification, logical_name)"
    )
    op.execute("ALTER TABLE ingestion_jobs DROP CONSTRAINT ck_ingestion_jobs_valid_status")
    op.execute(
        "ALTER TABLE ingestion_jobs ADD CONSTRAINT ck_ingestion_jobs_valid_status CHECK ("
        "status IN ('received', 'queued', 'running', 'succeeded', 'completed', "
        "'failed', 'cancelled', 'review_required'))"
    )
    op.execute(
        "ALTER TABLE ingestion_jobs ADD COLUMN current_stage varchar(32) "
        "NOT NULL DEFAULT 'received'"
    )
    op.execute(
        "ALTER TABLE ingestion_jobs ADD CONSTRAINT ck_ingestion_jobs_valid_stage CHECK ("
        "current_stage IN ('received', 'validating', 'storing', 'extracting', "
        "'normalizing', 'persisting', 'indexing', 'completed', 'failed', "
        "'review_required'))"
    )
    op.execute("ALTER TABLE ingestion_jobs ADD COLUMN error_count integer NOT NULL DEFAULT 0")
    op.execute(
        "ALTER TABLE ingestion_jobs ADD CONSTRAINT ck_ingestion_jobs_nonnegative_error_count "
        "CHECK (error_count >= 0)"
    )
    op.execute(
        "ALTER TABLE ingestion_jobs ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now()"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE ingestion_jobs DROP COLUMN updated_at")
    op.execute(
        "ALTER TABLE ingestion_jobs DROP CONSTRAINT ck_ingestion_jobs_nonnegative_error_count"
    )
    op.execute("ALTER TABLE ingestion_jobs DROP COLUMN error_count")
    op.execute("ALTER TABLE ingestion_jobs DROP CONSTRAINT ck_ingestion_jobs_valid_stage")
    op.execute("ALTER TABLE ingestion_jobs DROP COLUMN current_stage")
    op.execute("ALTER TABLE ingestion_jobs DROP CONSTRAINT ck_ingestion_jobs_valid_status")
    op.execute(
        "ALTER TABLE ingestion_jobs ADD CONSTRAINT ck_ingestion_jobs_valid_status CHECK ("
        "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled'))"
    )
    op.execute("ALTER TABLE documents DROP CONSTRAINT uq_documents_logical_scope_name")
