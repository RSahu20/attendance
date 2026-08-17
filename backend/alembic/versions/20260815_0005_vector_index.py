"""Add a cosine HNSW index for authorized semantic retrieval.

Revision ID: 20260815_0005
Revises: 20260815_0004
Create Date: 2026-08-15
"""

from alembic import op

revision: str = "20260815_0005"
down_revision: str | None = "20260815_0004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_chunk_embeddings_hnsw_cosine ON chunk_embeddings "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_chunk_embeddings_hnsw_cosine")
