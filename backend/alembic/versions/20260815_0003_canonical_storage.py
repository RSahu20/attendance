"""Add protected document, canonical attendance, FTS, and vector storage.

Revision ID: 20260815_0003
Revises: 20260815_0002
Create Date: 2026-08-15
"""

from alembic import op

revision: str = "20260815_0003"
down_revision: str | None = "20260815_0002"
branch_labels: str | None = None
depends_on: str | None = None


def create_protected_policies(table: str, read_permission: str, write_permission: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table}_scope_select ON {table}
        FOR SELECT USING (
            app_scope_allows(
                product_id, tenant_id, entity_id, module, classification, '{read_permission}'
            )
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY {table}_scope_insert ON {table}
        FOR INSERT WITH CHECK (
            app_scope_allows(
                product_id, tenant_id, entity_id, module, classification, '{write_permission}'
            )
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY {table}_scope_update ON {table}
        FOR UPDATE
        USING (
            app_scope_allows(
                product_id, tenant_id, entity_id, module, classification, '{write_permission}'
            )
        )
        WITH CHECK (
            app_scope_allows(
                product_id, tenant_id, entity_id, module, classification, '{write_permission}'
            )
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY {table}_scope_delete ON {table}
        FOR DELETE USING (
            app_scope_allows(
                product_id, tenant_id, entity_id, module, classification, '{write_permission}'
            )
        )
        """
    )


def upgrade() -> None:
    # Phase 2 supplied fully prefixed names to a metadata naming convention,
    # causing Alembic to prefix them twice. Normalize them before adding the
    # Phase 3 schema so future autogeneration stays stable.
    op.execute(
        "ALTER TABLE audit_events RENAME CONSTRAINT "
        "ck_audit_events_ck_audit_events_classification_range "
        "TO ck_audit_events_classification_range"
    )
    op.execute(
        "ALTER TABLE user_role_assignments RENAME CONSTRAINT "
        "ck_user_role_assignments_ck_user_role_assignments_class_e1e2 "
        "TO ck_user_role_assignments_classification_ceiling_range"
    )

    op.execute(
        """
        CREATE TABLE documents (
            id uuid PRIMARY KEY,
            product_id uuid NOT NULL,
            tenant_id uuid NOT NULL,
            entity_id uuid NOT NULL,
            module varchar(64) NOT NULL,
            classification integer NOT NULL,
            logical_name varchar(255) NOT NULL,
            is_active boolean NOT NULL DEFAULT true,
            created_by_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_documents_classification_range
                CHECK (classification BETWEEN 0 AND 3),
            CONSTRAINT fk_documents_entity_scope
                FOREIGN KEY (product_id, tenant_id, entity_id)
                REFERENCES entities (product_id, tenant_id, id) ON DELETE RESTRICT,
            CONSTRAINT fk_documents_created_by_user_id_users
                FOREIGN KEY (created_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
            CONSTRAINT uq_documents_protected_scope_id
                UNIQUE (product_id, tenant_id, entity_id, module, classification, id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_documents_scope ON documents (product_id, tenant_id, entity_id, module)"
    )

    op.execute(
        """
        CREATE TABLE document_versions (
            id uuid PRIMARY KEY,
            document_id uuid NOT NULL,
            product_id uuid NOT NULL,
            tenant_id uuid NOT NULL,
            entity_id uuid NOT NULL,
            module varchar(64) NOT NULL,
            classification integer NOT NULL,
            version_number integer NOT NULL,
            sha256 varchar(64) NOT NULL,
            source_filename varchar(255) NOT NULL,
            media_type varchar(255) NOT NULL,
            byte_size bigint NOT NULL,
            storage_key varchar(1024) NOT NULL,
            status varchar(32) NOT NULL DEFAULT 'pending',
            is_current boolean NOT NULL DEFAULT false,
            parser_name varchar(128),
            parser_version varchar(64),
            failure_code varchar(128),
            failure_detail text,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_by_user_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_document_versions_classification_range
                CHECK (classification BETWEEN 0 AND 3),
            CONSTRAINT ck_document_versions_positive_version_number
                CHECK (version_number > 0),
            CONSTRAINT ck_document_versions_nonnegative_byte_size CHECK (byte_size >= 0),
            CONSTRAINT ck_document_versions_sha256_length CHECK (char_length(sha256) = 64),
            CONSTRAINT ck_document_versions_valid_status CHECK (
                status IN (
                    'pending', 'processing', 'ready', 'review_required', 'failed', 'superseded'
                )
            ),
            CONSTRAINT fk_document_versions_protected_scope FOREIGN KEY (
                product_id, tenant_id, entity_id, module, classification, document_id
            ) REFERENCES documents (
                product_id, tenant_id, entity_id, module, classification, id
            ) ON DELETE CASCADE,
            CONSTRAINT fk_document_versions_created_by_user_id_users
                FOREIGN KEY (created_by_user_id) REFERENCES users (id) ON DELETE RESTRICT,
            CONSTRAINT uq_document_versions_number UNIQUE (document_id, version_number),
            CONSTRAINT uq_document_versions_checksum UNIQUE (document_id, sha256),
            CONSTRAINT uq_document_versions_protected_scope_id
                UNIQUE (product_id, tenant_id, entity_id, module, classification, id)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_document_versions_current "
        "ON document_versions (document_id) WHERE is_current"
    )
    op.execute(
        "CREATE INDEX ix_document_versions_scope ON document_versions "
        "(product_id, tenant_id, entity_id, module)"
    )

    op.execute(
        """
        CREATE TABLE ingestion_jobs (
            id uuid PRIMARY KEY,
            document_version_id uuid NOT NULL,
            product_id uuid NOT NULL,
            tenant_id uuid NOT NULL,
            entity_id uuid NOT NULL,
            module varchar(64) NOT NULL,
            classification integer NOT NULL,
            status varchar(32) NOT NULL DEFAULT 'queued',
            requested_by_user_id uuid NOT NULL,
            processed_units integer NOT NULL DEFAULT 0,
            accepted_records integer NOT NULL DEFAULT 0,
            review_records integer NOT NULL DEFAULT 0,
            error_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
            started_at timestamptz,
            completed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_ingestion_jobs_classification_range
                CHECK (classification BETWEEN 0 AND 3),
            CONSTRAINT ck_ingestion_jobs_valid_status
                CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
            CONSTRAINT ck_ingestion_jobs_nonnegative_counts CHECK (
                processed_units >= 0 AND accepted_records >= 0 AND review_records >= 0
            ),
            CONSTRAINT fk_ingestion_jobs_protected_scope FOREIGN KEY (
                product_id, tenant_id, entity_id, module, classification, document_version_id
            ) REFERENCES document_versions (
                product_id, tenant_id, entity_id, module, classification, id
            ) ON DELETE CASCADE,
            CONSTRAINT fk_ingestion_jobs_requested_by_user_id_users
                FOREIGN KEY (requested_by_user_id) REFERENCES users (id) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_ingestion_jobs_scope ON ingestion_jobs "
        "(product_id, tenant_id, entity_id, module)"
    )

    op.execute(
        """
        CREATE TABLE extracted_units (
            id uuid PRIMARY KEY,
            document_version_id uuid NOT NULL,
            product_id uuid NOT NULL,
            tenant_id uuid NOT NULL,
            entity_id uuid NOT NULL,
            module varchar(64) NOT NULL,
            classification integer NOT NULL,
            source_unit_key varchar(255) NOT NULL,
            unit_type varchar(64) NOT NULL,
            source_locator jsonb NOT NULL,
            raw_text text NOT NULL,
            structured_data jsonb NOT NULL DEFAULT '{}'::jsonb,
            extraction_method varchar(32) NOT NULL,
            extraction_confidence numeric(5, 4) NOT NULL,
            review_status varchar(32) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_extracted_units_classification_range
                CHECK (classification BETWEEN 0 AND 3),
            CONSTRAINT ck_extracted_units_confidence_range
                CHECK (extraction_confidence BETWEEN 0 AND 1),
            CONSTRAINT ck_extracted_units_valid_review_status
                CHECK (review_status IN ('accepted', 'review_required', 'rejected')),
            CONSTRAINT ck_extracted_units_valid_extraction_method CHECK (
                extraction_method IN ('native', 'csv', 'xlsx', 'docx', 'pdf_text', 'ocr', 'manual')
            ),
            CONSTRAINT fk_extracted_units_protected_scope FOREIGN KEY (
                product_id, tenant_id, entity_id, module, classification, document_version_id
            ) REFERENCES document_versions (
                product_id, tenant_id, entity_id, module, classification, id
            ) ON DELETE CASCADE,
            CONSTRAINT uq_extracted_units_source_key
                UNIQUE (document_version_id, source_unit_key),
            CONSTRAINT uq_extracted_units_protected_scope_id
                UNIQUE (product_id, tenant_id, entity_id, module, classification, id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_extracted_units_scope ON extracted_units "
        "(product_id, tenant_id, entity_id, module)"
    )

    op.execute(
        """
        CREATE TABLE attendance_records (
            id uuid PRIMARY KEY,
            product_id uuid NOT NULL,
            tenant_id uuid NOT NULL,
            entity_id uuid NOT NULL,
            module varchar(64) NOT NULL,
            classification integer NOT NULL,
            subject_external_id varchar(255) NOT NULL,
            subject_display_name varchar(255),
            attendance_date date NOT NULL,
            session_external_id varchar(255),
            session_name varchar(255),
            course_or_group varchar(255),
            status varchar(32) NOT NULL,
            scheduled_start timestamptz,
            scheduled_end timestamptz,
            check_in timestamptz,
            check_out timestamptz,
            scheduled_minutes integer,
            attended_minutes integer,
            attendance_percentage numeric(5, 2),
            late_minutes integer,
            source_document_id uuid NOT NULL,
            source_version_id uuid NOT NULL,
            source_unit_id uuid NOT NULL,
            source_record_key varchar(255) NOT NULL,
            raw_row_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            extraction_method varchar(32) NOT NULL,
            extraction_confidence numeric(5, 4) NOT NULL,
            review_status varchar(32) NOT NULL,
            normalization_warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
            recorded_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_attendance_records_classification_range
                CHECK (classification BETWEEN 0 AND 3),
            CONSTRAINT ck_attendance_records_valid_status CHECK (
                status IN ('present', 'absent', 'late', 'excused', 'partial', 'unknown')
            ),
            CONSTRAINT ck_attendance_records_valid_review_status
                CHECK (review_status IN ('accepted', 'review_required', 'rejected')),
            CONSTRAINT ck_attendance_records_valid_extraction_method CHECK (
                extraction_method IN ('native', 'csv', 'xlsx', 'docx', 'pdf_text', 'ocr', 'manual')
            ),
            CONSTRAINT ck_attendance_records_confidence_range
                CHECK (extraction_confidence BETWEEN 0 AND 1),
            CONSTRAINT ck_attendance_records_percentage_range CHECK (
                attendance_percentage IS NULL OR attendance_percentage BETWEEN 0 AND 100
            ),
            CONSTRAINT ck_attendance_records_nonnegative_scheduled_minutes
                CHECK (scheduled_minutes IS NULL OR scheduled_minutes >= 0),
            CONSTRAINT ck_attendance_records_nonnegative_attended_minutes
                CHECK (attended_minutes IS NULL OR attended_minutes >= 0),
            CONSTRAINT ck_attendance_records_nonnegative_late_minutes
                CHECK (late_minutes IS NULL OR late_minutes >= 0),
            CONSTRAINT ck_attendance_records_scheduled_time_order CHECK (
                scheduled_start IS NULL OR scheduled_end IS NULL OR scheduled_end >= scheduled_start
            ),
            CONSTRAINT ck_attendance_records_check_time_order
                CHECK (check_in IS NULL OR check_out IS NULL OR check_out >= check_in),
            CONSTRAINT fk_attendance_records_document_scope FOREIGN KEY (
                product_id, tenant_id, entity_id, module, classification, source_document_id
            ) REFERENCES documents (
                product_id, tenant_id, entity_id, module, classification, id
            ) ON DELETE CASCADE,
            CONSTRAINT fk_attendance_records_version_scope FOREIGN KEY (
                product_id, tenant_id, entity_id, module, classification, source_version_id
            ) REFERENCES document_versions (
                product_id, tenant_id, entity_id, module, classification, id
            ) ON DELETE CASCADE,
            CONSTRAINT fk_attendance_records_unit_scope FOREIGN KEY (
                product_id, tenant_id, entity_id, module, classification, source_unit_id
            ) REFERENCES extracted_units (
                product_id, tenant_id, entity_id, module, classification, id
            ) ON DELETE CASCADE,
            CONSTRAINT uq_attendance_records_source_key
                UNIQUE (source_version_id, source_record_key)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_attendance_records_scope_date ON attendance_records "
        "(product_id, tenant_id, entity_id, module, attendance_date)"
    )
    op.execute(
        "CREATE INDEX ix_attendance_records_subject_date ON attendance_records "
        "(subject_external_id, attendance_date)"
    )
    op.execute("CREATE INDEX ix_attendance_records_status ON attendance_records (status)")

    op.execute(
        """
        CREATE TABLE document_chunks (
            id uuid PRIMARY KEY,
            document_version_id uuid NOT NULL,
            extracted_unit_id uuid NOT NULL,
            product_id uuid NOT NULL,
            tenant_id uuid NOT NULL,
            entity_id uuid NOT NULL,
            module varchar(64) NOT NULL,
            classification integer NOT NULL,
            chunk_key varchar(255) NOT NULL,
            content text NOT NULL,
            source_locator jsonb NOT NULL,
            token_count integer NOT NULL,
            search_vector tsvector GENERATED ALWAYS AS (
                to_tsvector('english', coalesce(content, ''))
            ) STORED NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_document_chunks_classification_range
                CHECK (classification BETWEEN 0 AND 3),
            CONSTRAINT ck_document_chunks_nonnegative_token_count CHECK (token_count >= 0),
            CONSTRAINT fk_document_chunks_version_scope FOREIGN KEY (
                product_id, tenant_id, entity_id, module, classification, document_version_id
            ) REFERENCES document_versions (
                product_id, tenant_id, entity_id, module, classification, id
            ) ON DELETE CASCADE,
            CONSTRAINT fk_document_chunks_unit_scope FOREIGN KEY (
                product_id, tenant_id, entity_id, module, classification, extracted_unit_id
            ) REFERENCES extracted_units (
                product_id, tenant_id, entity_id, module, classification, id
            ) ON DELETE CASCADE,
            CONSTRAINT uq_document_chunks_key UNIQUE (document_version_id, chunk_key),
            CONSTRAINT uq_document_chunks_protected_scope_id
                UNIQUE (product_id, tenant_id, entity_id, module, classification, id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_scope ON document_chunks "
        "(product_id, tenant_id, entity_id, module)"
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_search_vector ON document_chunks USING gin (search_vector)"
    )

    op.execute(
        """
        CREATE TABLE chunk_embeddings (
            id uuid PRIMARY KEY,
            chunk_id uuid NOT NULL,
            product_id uuid NOT NULL,
            tenant_id uuid NOT NULL,
            entity_id uuid NOT NULL,
            module varchar(64) NOT NULL,
            classification integer NOT NULL,
            model_name varchar(255) NOT NULL,
            model_version varchar(128) NOT NULL,
            embedding vector(384) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_chunk_embeddings_classification_range
                CHECK (classification BETWEEN 0 AND 3),
            CONSTRAINT fk_chunk_embeddings_protected_scope FOREIGN KEY (
                product_id, tenant_id, entity_id, module, classification, chunk_id
            ) REFERENCES document_chunks (
                product_id, tenant_id, entity_id, module, classification, id
            ) ON DELETE CASCADE,
            CONSTRAINT uq_chunk_embeddings_model UNIQUE (chunk_id, model_name, model_version)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_chunk_embeddings_scope ON chunk_embeddings "
        "(product_id, tenant_id, entity_id, module)"
    )

    for table in (
        "documents",
        "document_versions",
        "ingestion_jobs",
        "extracted_units",
        "document_chunks",
        "chunk_embeddings",
    ):
        create_protected_policies(table, "document:read", "document:write")
    create_protected_policies("attendance_records", "attendance:read", "attendance:write")


def downgrade() -> None:
    op.execute("DROP TABLE chunk_embeddings")
    op.execute("DROP TABLE document_chunks")
    op.execute("DROP TABLE attendance_records")
    op.execute("DROP TABLE extracted_units")
    op.execute("DROP TABLE ingestion_jobs")
    op.execute("DROP TABLE document_versions")
    op.execute("DROP TABLE documents")
    op.execute(
        "ALTER TABLE audit_events RENAME CONSTRAINT "
        "ck_audit_events_classification_range "
        "TO ck_audit_events_ck_audit_events_classification_range"
    )
    op.execute(
        "ALTER TABLE user_role_assignments RENAME CONSTRAINT "
        "ck_user_role_assignments_classification_ceiling_range "
        "TO ck_user_role_assignments_ck_user_role_assignments_class_e1e2"
    )
