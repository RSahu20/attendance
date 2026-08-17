from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from attendance.db.base import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("classification BETWEEN 0 AND 3", name="classification_range"),
        ForeignKeyConstraint(
            ["product_id", "tenant_id", "entity_id"],
            ["entities.product_id", "entities.tenant_id", "entities.id"],
            name="fk_documents_entity_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "product_id",
            "tenant_id",
            "entity_id",
            "module",
            "classification",
            "id",
            name="uq_documents_protected_scope_id",
        ),
        UniqueConstraint(
            "product_id",
            "tenant_id",
            "entity_id",
            "module",
            "classification",
            "logical_name",
            name="uq_documents_logical_scope_name",
        ),
        Index("ix_documents_scope", "product_id", "tenant_id", "entity_id", "module"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    classification: Mapped[int] = mapped_column(Integer, nullable=False)
    logical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        CheckConstraint("classification BETWEEN 0 AND 3", name="classification_range"),
        CheckConstraint("version_number > 0", name="positive_version_number"),
        CheckConstraint("byte_size >= 0", name="nonnegative_byte_size"),
        CheckConstraint("char_length(sha256) = 64", name="sha256_length"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'review_required', "
            "'failed', 'superseded')",
            name="valid_status",
        ),
        ForeignKeyConstraint(
            [
                "product_id",
                "tenant_id",
                "entity_id",
                "module",
                "classification",
                "document_id",
            ],
            [
                "documents.product_id",
                "documents.tenant_id",
                "documents.entity_id",
                "documents.module",
                "documents.classification",
                "documents.id",
            ],
            name="fk_document_versions_protected_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint("document_id", "version_number", name="uq_document_versions_number"),
        UniqueConstraint("document_id", "sha256", name="uq_document_versions_checksum"),
        Index(
            "uq_document_versions_current",
            "document_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        UniqueConstraint(
            "product_id",
            "tenant_id",
            "entity_id",
            "module",
            "classification",
            "id",
            name="uq_document_versions_protected_scope_id",
        ),
        Index(
            "ix_document_versions_scope",
            "product_id",
            "tenant_id",
            "entity_id",
            "module",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    classification: Mapped[int] = mapped_column(Integer, nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parser_name: Mapped[str | None] = mapped_column(String(128))
    parser_version: Mapped[str | None] = mapped_column(String(64))
    failure_code: Mapped[str | None] = mapped_column(String(128))
    failure_detail: Mapped[str | None] = mapped_column(Text)
    version_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint("classification BETWEEN 0 AND 3", name="classification_range"),
        CheckConstraint(
            "status IN ('received', 'queued', 'running', 'succeeded', 'completed', "
            "'failed', 'cancelled', 'review_required')",
            name="valid_status",
        ),
        CheckConstraint(
            "current_stage IN ('received', 'validating', 'storing', 'extracting', "
            "'normalizing', 'persisting', 'indexing', 'completed', 'failed', "
            "'review_required')",
            name="valid_stage",
        ),
        CheckConstraint(
            "processed_units >= 0 AND accepted_records >= 0 AND review_records >= 0",
            name="nonnegative_counts",
        ),
        CheckConstraint("error_count >= 0", name="nonnegative_error_count"),
        ForeignKeyConstraint(
            [
                "product_id",
                "tenant_id",
                "entity_id",
                "module",
                "classification",
                "document_version_id",
            ],
            [
                "document_versions.product_id",
                "document_versions.tenant_id",
                "document_versions.entity_id",
                "document_versions.module",
                "document_versions.classification",
                "document_versions.id",
            ],
            name="fk_ingestion_jobs_protected_scope",
            ondelete="CASCADE",
        ),
        Index("ix_ingestion_jobs_scope", "product_id", "tenant_id", "entity_id", "module"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    document_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    classification: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="received")
    current_stage: Mapped[str] = mapped_column(String(32), nullable=False, default="received")
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    processed_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ExtractedUnit(Base):
    __tablename__ = "extracted_units"
    __table_args__ = (
        CheckConstraint("classification BETWEEN 0 AND 3", name="classification_range"),
        CheckConstraint("extraction_confidence BETWEEN 0 AND 1", name="confidence_range"),
        CheckConstraint(
            "review_status IN ('accepted', 'review_required', 'rejected')",
            name="valid_review_status",
        ),
        CheckConstraint(
            "extraction_method IN ('native', 'csv', 'xlsx', 'docx', 'pdf_text', 'ocr', 'manual')",
            name="valid_extraction_method",
        ),
        ForeignKeyConstraint(
            [
                "product_id",
                "tenant_id",
                "entity_id",
                "module",
                "classification",
                "document_version_id",
            ],
            [
                "document_versions.product_id",
                "document_versions.tenant_id",
                "document_versions.entity_id",
                "document_versions.module",
                "document_versions.classification",
                "document_versions.id",
            ],
            name="fk_extracted_units_protected_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "document_version_id", "source_unit_key", name="uq_extracted_units_source_key"
        ),
        UniqueConstraint(
            "product_id",
            "tenant_id",
            "entity_id",
            "module",
            "classification",
            "id",
            name="uq_extracted_units_protected_scope_id",
        ),
        Index("ix_extracted_units_scope", "product_id", "tenant_id", "entity_id", "module"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    document_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    classification: Mapped[int] = mapped_column(Integer, nullable=False)
    source_unit_key: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_locator: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    structured_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    extraction_method: Mapped[str] = mapped_column(String(32), nullable=False)
    extraction_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        CheckConstraint("classification BETWEEN 0 AND 3", name="classification_range"),
        CheckConstraint("token_count >= 0", name="nonnegative_token_count"),
        ForeignKeyConstraint(
            [
                "product_id",
                "tenant_id",
                "entity_id",
                "module",
                "classification",
                "document_version_id",
            ],
            [
                "document_versions.product_id",
                "document_versions.tenant_id",
                "document_versions.entity_id",
                "document_versions.module",
                "document_versions.classification",
                "document_versions.id",
            ],
            name="fk_document_chunks_version_scope",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            [
                "product_id",
                "tenant_id",
                "entity_id",
                "module",
                "classification",
                "extracted_unit_id",
            ],
            [
                "extracted_units.product_id",
                "extracted_units.tenant_id",
                "extracted_units.entity_id",
                "extracted_units.module",
                "extracted_units.classification",
                "extracted_units.id",
            ],
            name="fk_document_chunks_unit_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint("document_version_id", "chunk_key", name="uq_document_chunks_key"),
        UniqueConstraint(
            "product_id",
            "tenant_id",
            "entity_id",
            "module",
            "classification",
            "id",
            name="uq_document_chunks_protected_scope_id",
        ),
        Index("ix_document_chunks_scope", "product_id", "tenant_id", "entity_id", "module"),
        Index("ix_document_chunks_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    document_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    extracted_unit_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    classification: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_key: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_locator: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(content, ''))", persisted=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChunkEmbedding(Base):
    __tablename__ = "chunk_embeddings"
    __table_args__ = (
        CheckConstraint("classification BETWEEN 0 AND 3", name="classification_range"),
        ForeignKeyConstraint(
            [
                "product_id",
                "tenant_id",
                "entity_id",
                "module",
                "classification",
                "chunk_id",
            ],
            [
                "document_chunks.product_id",
                "document_chunks.tenant_id",
                "document_chunks.entity_id",
                "document_chunks.module",
                "document_chunks.classification",
                "document_chunks.id",
            ],
            name="fk_chunk_embeddings_protected_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "chunk_id", "model_name", "model_version", name="uq_chunk_embeddings_model"
        ),
        Index("ix_chunk_embeddings_scope", "product_id", "tenant_id", "entity_id", "module"),
        Index(
            "ix_chunk_embeddings_hnsw_cosine",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    chunk_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    classification: Mapped[int] = mapped_column(Integer, nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
