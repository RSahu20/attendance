from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Any

import jwt
import pytest
from docx import Document as OpenDocument
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from attendance.config import get_settings
from attendance.main import app
from tests.integration.conftest import SecuritySeed


def token_for(subject: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": subject,
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def headers(seed: SecuritySeed, tenant_id: str | None = None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token_for(seed.subject)}",
        "X-Product-ID": str(seed.product_id),
        "X-Tenant-ID": tenant_id or str(seed.tenant_a_id),
    }


def attendance_csv(employee: str = "EMP-100", status: str = "Present") -> bytes:
    return (
        "Date,Employee ID,Employee Name,Status,Department,Check In,Check Out,Total Hours\n"
        f"2026-08-01,{employee},Fictional Person,{status},Engineering,09:00,17:00,8\n"
    ).encode()


def unrelated_docx() -> bytes:
    document = OpenDocument()
    document.add_paragraph("Architecture implementation plan without attendance evidence.")
    output = BytesIO()
    document.save(output)
    return output.getvalue()


@pytest.fixture
def ingestion_seed(
    security_seed: SecuritySeed, migration_database_url: str
) -> Iterator[SecuritySeed]:
    yield security_seed
    engine = create_engine(migration_database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM documents WHERE product_id = :product_id"),
                {"product_id": security_seed.product_id},
            )
            connection.execute(text("TRUNCATE audit_events"))
    finally:
        engine.dispose()


def upload(
    client: TestClient,
    seed: SecuritySeed,
    content: bytes,
    *,
    filename: str = "attendance.csv",
    logical_name: str = "monthly-attendance",
    entity_id: str | None = None,
    classification: str = "2",
) -> Any:
    return client.post(
        "/api/v1/documents",
        headers=headers(seed),
        files={"file": (filename, content, "text/csv")},
        data={
            "entity_id": entity_id or str(seed.entity_high_id),
            "module": "attendance",
            "classification": classification,
            "logical_name": logical_name,
        },
    )


@pytest.mark.integration
def test_csv_upload_persists_records_lineage_chunks_and_job_status(
    ingestion_seed: SecuritySeed, migration_database_url: str
) -> None:
    with TestClient(app) as client:
        response = upload(client, ingestion_seed, attendance_csv())
        assert response.status_code == 201, response.text
        payload = response.json()
        job = client.get(
            f"/api/v1/ingestion-jobs/{payload['job_id']}", headers=headers(ingestion_seed)
        )

    assert payload["status"] == "completed"
    assert job.status_code == 200
    assert job.json()["normalized_record_count"] == 1
    assert job.json()["extracted_unit_count"] == 1

    engine = create_engine(migration_database_url)
    try:
        with engine.connect() as connection:
            record = connection.execute(
                text(
                    "SELECT subject_external_id, status, course_or_group, raw_row_metadata "
                    "FROM attendance_records WHERE source_version_id = :version_id"
                ),
                {"version_id": payload["document_version_id"]},
            ).one()
            unit_locator = connection.scalar(
                text(
                    "SELECT source_locator FROM extracted_units "
                    "WHERE document_version_id = :version_id"
                ),
                {"version_id": payload["document_version_id"]},
            )
            chunk_count = connection.scalar(
                text(
                    "SELECT count(*) FROM document_chunks "
                    "WHERE document_version_id = :version_id AND search_vector IS NOT NULL"
                ),
                {"version_id": payload["document_version_id"]},
            )
    finally:
        engine.dispose()

    assert record[0:3] == ("EMP-100", "present", "Engineering")
    assert record.raw_row_metadata["row"] == 2
    assert unit_locator == {"file": "attendance.csv", "row": 2}
    assert chunk_count == 1


@pytest.mark.integration
def test_same_file_is_idempotent_without_duplicate_records(
    ingestion_seed: SecuritySeed, migration_database_url: str
) -> None:
    with TestClient(app) as client:
        first = upload(client, ingestion_seed, attendance_csv()).json()
        second = upload(client, ingestion_seed, attendance_csv()).json()

    engine = create_engine(migration_database_url)
    try:
        with engine.connect() as connection:
            version_count = connection.scalar(
                text("SELECT count(*) FROM document_versions WHERE document_id = :document_id"),
                {"document_id": first["document_id"]},
            )
            record_count = connection.scalar(
                text("SELECT count(*) FROM attendance_records WHERE source_document_id = :id"),
                {"id": first["document_id"]},
            )
    finally:
        engine.dispose()

    assert second["idempotent"] is True
    assert second["document_version_id"] == first["document_version_id"]
    assert version_count == 1
    assert record_count == 1


@pytest.mark.integration
def test_changed_file_creates_new_current_version(
    ingestion_seed: SecuritySeed, migration_database_url: str
) -> None:
    with TestClient(app) as client:
        first = upload(client, ingestion_seed, attendance_csv("EMP-101")).json()
        second = upload(client, ingestion_seed, attendance_csv("EMP-102")).json()

    engine = create_engine(migration_database_url)
    try:
        with engine.connect() as connection:
            versions = connection.execute(
                text(
                    "SELECT id, version_number, is_current, status FROM document_versions "
                    "WHERE document_id = :document_id ORDER BY version_number"
                ),
                {"document_id": first["document_id"]},
            ).all()
    finally:
        engine.dispose()

    assert second["document_version_id"] != first["document_version_id"]
    assert [(row.version_number, row.is_current) for row in versions] == [(1, False), (2, True)]
    assert versions[0].status == "superseded"


@pytest.mark.integration
def test_invalid_file_failure_is_queryable(
    ingestion_seed: SecuritySeed,
) -> None:
    with TestClient(app) as client:
        response = upload(
            client,
            ingestion_seed,
            b"not supported",
            filename="attendance.txt",
            logical_name="bad-input",
        )
        payload = response.json()
        job = client.get(
            f"/api/v1/ingestion-jobs/{payload['job_id']}", headers=headers(ingestion_seed)
        )

    assert response.status_code == 201
    assert payload["status"] == "failed"
    assert job.json()["current_stage"] == "failed"
    assert job.json()["errors"][0]["code"] == "unsupported_file_type"


@pytest.mark.integration
def test_non_attendance_document_is_quarantined_without_search_chunks(
    ingestion_seed: SecuritySeed, migration_database_url: str
) -> None:
    with TestClient(app) as client:
        response = upload(
            client,
            ingestion_seed,
            unrelated_docx(),
            filename="architecture.docx",
            logical_name="unrelated-architecture",
        )
        payload = response.json()
        job = client.get(
            f"/api/v1/ingestion-jobs/{payload['job_id']}", headers=headers(ingestion_seed)
        )

    assert response.status_code == 201
    assert payload["status"] == "review_required"
    assert job.status_code == 200
    assert job.json()["status"] == "review_required"
    assert job.json()["normalized_record_count"] == 0
    assert job.json()["review_required_count"] == 1
    assert job.json()["errors"][0]["code"] == "no_attendance_data_detected"

    engine = create_engine(migration_database_url)
    try:
        with engine.connect() as connection:
            unit_status = connection.scalar(
                text(
                    "SELECT review_status FROM extracted_units "
                    "WHERE document_version_id = :version_id"
                ),
                {"version_id": payload["document_version_id"]},
            )
            chunk_count = connection.scalar(
                text(
                    "SELECT count(*) FROM document_chunks WHERE document_version_id = :version_id"
                ),
                {"version_id": payload["document_version_id"]},
            )
    finally:
        engine.dispose()

    assert unit_status == "review_required"
    assert chunk_count == 0


@pytest.mark.integration
def test_non_attendance_csv_has_specific_failure_reason(ingestion_seed: SecuritySeed) -> None:
    with TestClient(app) as client:
        response = upload(
            client,
            ingestion_seed,
            b"agent_id,agent_name,capability\nAG-001,Planner,orchestration\n",
            filename="agent_registry.csv",
            logical_name="agent-registry",
        )
        payload = response.json()
        job = client.get(
            f"/api/v1/ingestion-jobs/{payload['job_id']}", headers=headers(ingestion_seed)
        )

    assert response.status_code == 201
    assert payload["status"] == "failed"
    assert job.json()["errors"][0]["code"] == "no_attendance_header"


@pytest.mark.integration
def test_upload_authorization_and_tenant_isolation(ingestion_seed: SecuritySeed) -> None:
    with TestClient(app) as client:
        denied_upload = upload(
            client,
            ingestion_seed,
            attendance_csv(),
            entity_id=str(ingestion_seed.entity_low_id),
            classification="2",
        )
        allowed = upload(client, ingestion_seed, attendance_csv(), logical_name="isolated").json()
        cross_tenant = client.get(
            f"/api/v1/ingestion-jobs/{allowed['job_id']}",
            headers=headers(ingestion_seed, str(ingestion_seed.tenant_b_id)),
        )

    assert denied_upload.status_code == 403
    assert denied_upload.json() == {"detail": "Requested scope is unavailable"}
    assert cross_tenant.status_code == 403
    assert cross_tenant.json() == {"detail": "Requested scope is unavailable"}
