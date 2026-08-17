"""Enable and verify the pgvector extension.

Revision ID: 20260815_0001
Revises:
Create Date: 2026-08-15
"""

from alembic import op

revision: str = "20260815_0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_extension WHERE extname = 'vector'
            ) THEN
                RAISE EXCEPTION 'pgvector extension is required but unavailable';
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    # The extension can be shared by future tables and other applications. Removing
    # it automatically during a downgrade would be unexpectedly destructive.
    pass
