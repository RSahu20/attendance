from decimal import Decimal
from uuid import uuid4

from attendance.domain.attendance import ExtractionMethod, ReviewStatus
from attendance.domain.security import ClassificationLevel
from attendance.ingestion.checksum import sha256_hex
from attendance.ingestion.normalization import AttendanceNormalizer, NormalizationContext
from attendance.ingestion.types import ParsedUnit


def context() -> NormalizationContext:
    return NormalizationContext(
        product_id=uuid4(),
        tenant_id=uuid4(),
        entity_id=uuid4(),
        module="attendance",
        classification=ClassificationLevel.CONFIDENTIAL,
        document_id=uuid4(),
        document_version_id=uuid4(),
        extracted_unit_id=uuid4(),
        filename="sample.csv",
    )


def test_checksum_is_stable_and_content_sensitive() -> None:
    assert sha256_hex(b"attendance") == sha256_hex(b"attendance")
    assert sha256_hex(b"attendance") != sha256_hex(b"changed")


def test_normalizer_creates_canonical_record_and_source_lineage() -> None:
    unit = ParsedUnit(
        source_unit_key="csv:row:2",
        unit_type="attendance_row",
        source_locator={"file": "sample.csv", "row": 2},
        raw_text="2026-08-01 | EMP-001 | WFH",
        structured_data={
            "attendance_date": "2026-08-01",
            "employee_id": "EMP-001",
            "employee_name": "Asha Fiction",
            "status": "WFH",
            "department": "Engineering",
            "check_in": "09:00",
            "check_out": "17:30",
            "total_hours": "8.5",
            "attendance_percentage": "100%",
        },
        extraction_method=ExtractionMethod.CSV,
    )

    outcome = AttendanceNormalizer().normalize(unit, context())

    assert outcome.issue is None
    assert outcome.record is not None
    assert outcome.record.subject_external_id == "EMP-001"
    assert outcome.record.attended_minutes == 510
    assert outcome.record.attendance_percentage == Decimal("100")
    assert outcome.record.raw_row_metadata["source_file"] == "sample.csv"
    assert outcome.record.raw_row_metadata["row"] == 2
    assert outcome.record.normalization_warnings


def test_normalizer_returns_structured_issue_for_invalid_record() -> None:
    unit = ParsedUnit(
        source_unit_key="csv:row:9",
        unit_type="attendance_row",
        source_locator={"file": "bad.csv", "row": 9},
        raw_text="bad",
        structured_data={
            "attendance_date": "not-a-date",
            "employee_id": "EMP-009",
            "status": "Present",
        },
        extraction_method=ExtractionMethod.CSV,
        review_status=ReviewStatus.ACCEPTED,
    )

    outcome = AttendanceNormalizer().normalize(unit, context())

    assert outcome.record is None
    assert outcome.issue is not None
    assert outcome.issue.source_unit_key == "csv:row:9"
    assert outcome.issue.code == "normalization_invalid"
