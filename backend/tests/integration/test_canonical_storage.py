import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from attendance.db.models.attendance import AttendanceRecord
from attendance.db.models.documents import (
    ChunkEmbedding,
    Document,
    DocumentChunk,
    DocumentVersion,
    ExtractedUnit,
)
from attendance.db.rls import set_authorization_context
from attendance.domain.security import ClassificationLevel
from attendance.security.authentication import Principal
from attendance.security.authorization import AuthorizationService
from tests.integration.conftest import SecuritySeed


@dataclass
class ProtectedStorageSeed:
    session: Session
    document_id: UUID
    version_id: UUID
    unit_id: UUID
    attendance_id: UUID
    chunk_id: UUID
    embedding_id: UUID


@pytest.fixture
def protected_storage_seed(
    database_url: str, security_seed: SecuritySeed
) -> Iterator[ProtectedStorageSeed]:
    engine = create_engine(database_url)
    session = Session(engine)
    try:
        scope = AuthorizationService().resolve_scope(
            session,
            Principal(subject=security_seed.subject),
            product_id=security_seed.product_id,
            tenant_id=security_seed.tenant_a_id,
        )
        set_authorization_context(session, scope)
        protected_scope = {
            "product_id": security_seed.product_id,
            "tenant_id": security_seed.tenant_a_id,
            "entity_id": security_seed.entity_high_id,
            "module": "attendance",
            "classification": int(ClassificationLevel.CONFIDENTIAL),
        }

        document = Document(
            **protected_scope,
            logical_name="Storage Test Document",
            created_by_user_id=security_seed.user_id,
        )
        session.add(document)
        session.flush()

        version = DocumentVersion(
            **protected_scope,
            document_id=document.id,
            version_number=1,
            sha256="a" * 64,
            source_filename="attendance.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            byte_size=128,
            storage_key="test/storage/attendance.xlsx",
            status="ready",
            is_current=True,
            version_metadata={},
            created_by_user_id=security_seed.user_id,
        )
        session.add(version)
        session.flush()

        unit = ExtractedUnit(
            **protected_scope,
            document_version_id=version.id,
            source_unit_key="sheet-1-row-2",
            unit_type="row",
            source_locator={"sheet": "Sheet1", "row": 2},
            raw_text="Student one was present for the attendance policy session",
            structured_data={"status": "present"},
            extraction_method="xlsx",
            extraction_confidence=Decimal("0.9900"),
            review_status="accepted",
        )
        session.add(unit)
        session.flush()

        attendance = AttendanceRecord(
            **protected_scope,
            subject_external_id="subject-001",
            attendance_date=date(2026, 8, 15),
            status="present",
            attendance_percentage=Decimal("100.00"),
            source_document_id=document.id,
            source_version_id=version.id,
            source_unit_id=unit.id,
            source_record_key="sheet-1-row-2",
            raw_row_metadata={},
            extraction_method="xlsx",
            extraction_confidence=Decimal("0.9900"),
            review_status="accepted",
            normalization_warnings=[],
        )
        session.add(attendance)

        chunk = DocumentChunk(
            **protected_scope,
            document_version_id=version.id,
            extracted_unit_id=unit.id,
            chunk_key="sheet-1-row-2-chunk-1",
            content="Student one was present for the attendance policy session",
            source_locator={"sheet": "Sheet1", "row": 2},
            token_count=9,
        )
        session.add(chunk)
        session.flush()

        embedding = ChunkEmbedding(
            **protected_scope,
            chunk_id=chunk.id,
            model_name="test-model",
            model_version="1",
            embedding=[0.0] * 384,
        )
        session.add(embedding)
        session.flush()

        yield ProtectedStorageSeed(
            session=session,
            document_id=document.id,
            version_id=version.id,
            unit_id=unit.id,
            attendance_id=attendance.id,
            chunk_id=chunk.id,
            embedding_id=embedding.id,
        )
    finally:
        session.rollback()
        session.close()
        engine.dispose()


@pytest.mark.integration
def test_fts_and_vector_columns_are_operational(
    protected_storage_seed: ProtectedStorageSeed,
) -> None:
    session = protected_storage_seed.session
    fts_match = session.scalar(
        select(DocumentChunk.id).where(
            DocumentChunk.id == protected_storage_seed.chunk_id,
            DocumentChunk.search_vector.op("@@")(
                func.plainto_tsquery("english", "attendance policy")
            ),
        )
    )
    dimensions = session.scalar(
        select(func.vector_dims(ChunkEmbedding.embedding)).where(
            ChunkEmbedding.id == protected_storage_seed.embedding_id
        )
    )

    assert fts_match == protected_storage_seed.chunk_id
    assert dimensions == 384


@pytest.mark.integration
def test_attendance_database_constraints_reject_invalid_percentage(
    protected_storage_seed: ProtectedStorageSeed,
) -> None:
    session = protected_storage_seed.session
    record = session.get(AttendanceRecord, protected_storage_seed.attendance_id)
    assert record is not None
    record.attendance_percentage = Decimal("101.00")

    with pytest.raises(DBAPIError, match="percentage_range"):
        session.flush()


@pytest.mark.integration
def test_document_checksum_is_idempotent_within_logical_document(
    protected_storage_seed: ProtectedStorageSeed,
) -> None:
    session = protected_storage_seed.session
    original = session.get(DocumentVersion, protected_storage_seed.version_id)
    assert original is not None
    duplicate = DocumentVersion(
        document_id=original.document_id,
        product_id=original.product_id,
        tenant_id=original.tenant_id,
        entity_id=original.entity_id,
        module=original.module,
        classification=original.classification,
        version_number=2,
        sha256=original.sha256,
        source_filename="duplicate.xlsx",
        media_type=original.media_type,
        byte_size=original.byte_size,
        storage_key="test/storage/duplicate.xlsx",
        status="pending",
        is_current=False,
        version_metadata={},
        created_by_user_id=original.created_by_user_id,
    )
    session.add(duplicate)

    with pytest.raises(DBAPIError, match="uq_document_versions_checksum"):
        session.flush()


@pytest.mark.integration
def test_protected_tables_have_operation_specific_rls_policies(database_url: str) -> None:
    protected_tables = (
        "documents",
        "document_versions",
        "ingestion_jobs",
        "extracted_units",
        "attendance_records",
        "document_chunks",
        "chunk_embeddings",
    )
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            policy_counts = dict(
                connection.execute(
                    text(
                        """
                        SELECT tablename, count(*)
                        FROM pg_policies
                        WHERE tablename = ANY(:tables)
                        GROUP BY tablename
                        """
                    ),
                    {"tables": list(protected_tables)},
                ).all()
            )
            rls_tables = set(
                connection.scalars(
                    text(
                        """
                        SELECT relname
                        FROM pg_class
                        WHERE relname = ANY(:tables) AND relrowsecurity
                        """
                    ),
                    {"tables": list(protected_tables)},
                ).all()
            )
    finally:
        engine.dispose()

    assert rls_tables == set(protected_tables)
    assert policy_counts == {table: 4 for table in protected_tables}


@pytest.mark.integration
def test_runtime_role_cannot_read_document_from_another_entity(
    migration_database_url: str,
    runtime_database_user: str,
    security_seed: SecuritySeed,
) -> None:
    engine = create_engine(migration_database_url)
    connection = engine.connect()
    transaction = connection.begin()
    high_document_id = uuid4()
    low_document_id = uuid4()
    try:
        for document_id, entity_id in (
            (high_document_id, security_seed.entity_high_id),
            (low_document_id, security_seed.entity_low_id),
        ):
            connection.execute(
                text(
                    """
                    INSERT INTO documents (
                        id, product_id, tenant_id, entity_id, module, classification,
                        logical_name, created_by_user_id
                    ) VALUES (
                        :id, :product_id, :tenant_id, :entity_id, 'attendance', 0,
                        'RLS test document', :user_id
                    )
                    """
                ),
                {
                    "id": document_id,
                    "product_id": security_seed.product_id,
                    "tenant_id": security_seed.tenant_a_id,
                    "entity_id": entity_id,
                    "user_id": security_seed.user_id,
                },
            )
        connection.execute(
            text("SELECT set_config('role', :role_name, true)"),
            {"role_name": runtime_database_user},
        )
        grants = json.dumps(
            [
                {
                    "entity_id": str(security_seed.entity_high_id),
                    "module": "attendance",
                    "classification_ceiling": 0,
                    "permissions": ["document:read"],
                }
            ]
        )
        connection.execute(
            text(
                """
                SELECT
                    set_config('app.product_id', :product_id, true),
                    set_config('app.tenant_id', :tenant_id, true),
                    set_config('app.authorization_grants', :grants, true)
                """
            ),
            {
                "product_id": str(security_seed.product_id),
                "tenant_id": str(security_seed.tenant_a_id),
                "grants": grants,
            },
        )
        visible_documents = set(
            connection.scalars(
                text("SELECT id FROM documents WHERE id IN (:high_id, :low_id)"),
                {"high_id": high_document_id, "low_id": low_document_id},
            ).all()
        )
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()

    assert visible_documents == {high_document_id}


@pytest.mark.integration
def test_document_version_cannot_cross_protected_scope(
    migration_database_url: str, security_seed: SecuritySeed
) -> None:
    engine = create_engine(migration_database_url)
    connection = engine.connect()
    transaction = connection.begin()
    document_id = uuid4()
    try:
        connection.execute(
            text(
                """
                INSERT INTO documents (
                    id, product_id, tenant_id, entity_id, module, classification,
                    logical_name, created_by_user_id
                ) VALUES (
                    :id, :product_id, :tenant_id, :entity_id, 'attendance', 0,
                    'Scope consistency test', :user_id
                )
                """
            ),
            {
                "id": document_id,
                "product_id": security_seed.product_id,
                "tenant_id": security_seed.tenant_a_id,
                "entity_id": security_seed.entity_high_id,
                "user_id": security_seed.user_id,
            },
        )

        with pytest.raises(DBAPIError, match="fk_document_versions_protected_scope"):
            connection.execute(
                text(
                    """
                    INSERT INTO document_versions (
                        id, document_id, product_id, tenant_id, entity_id, module,
                        classification, version_number, sha256, source_filename,
                        media_type, byte_size, storage_key, created_by_user_id
                    ) VALUES (
                        :id, :document_id, :product_id, :tenant_id, :wrong_entity_id,
                        'attendance', 0, 1, :sha256, 'test.csv', 'text/csv', 1,
                        'test/test.csv', :user_id
                    )
                    """
                ),
                {
                    "id": uuid4(),
                    "document_id": document_id,
                    "product_id": security_seed.product_id,
                    "tenant_id": security_seed.tenant_a_id,
                    "wrong_entity_id": security_seed.entity_low_id,
                    "sha256": "b" * 64,
                    "user_id": security_seed.user_id,
                },
            )
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()
