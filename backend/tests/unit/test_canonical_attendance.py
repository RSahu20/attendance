from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from attendance.domain.attendance import (
    AttendanceStatus,
    CanonicalAttendanceRecord,
    ExtractionMethod,
    ReviewStatus,
)
from attendance.domain.security import ClassificationLevel


def make_record(**overrides: object) -> CanonicalAttendanceRecord:
    start = datetime(2026, 8, 15, 9, 0, tzinfo=UTC)
    values: dict[str, object] = {
        "product_id": uuid4(),
        "tenant_id": uuid4(),
        "entity_id": uuid4(),
        "module": "attendance",
        "classification": ClassificationLevel.INTERNAL,
        "subject_external_id": "subject-001",
        "attendance_date": date(2026, 8, 15),
        "status": AttendanceStatus.PRESENT,
        "scheduled_start": start,
        "scheduled_end": start + timedelta(hours=1),
        "scheduled_minutes": 60,
        "attended_minutes": 60,
        "attendance_percentage": Decimal("100"),
        "source_document_id": uuid4(),
        "source_version_id": uuid4(),
        "source_unit_id": uuid4(),
        "source_record_key": "sheet-1-row-2",
        "extraction_method": ExtractionMethod.XLSX,
        "extraction_confidence": Decimal("0.99"),
        "review_status": ReviewStatus.ACCEPTED,
    }
    values.update(overrides)
    return CanonicalAttendanceRecord.model_validate(values)


def test_canonical_attendance_record_accepts_valid_fact() -> None:
    record = make_record()

    assert record.status is AttendanceStatus.PRESENT
    assert record.attendance_percentage == Decimal("100")


def test_canonical_attendance_record_rejects_invalid_time_order() -> None:
    start = datetime(2026, 8, 15, 9, 0, tzinfo=UTC)

    with pytest.raises(ValidationError, match="scheduled_end cannot precede"):
        make_record(scheduled_start=start, scheduled_end=start - timedelta(minutes=1))


def test_canonical_attendance_record_rejects_invalid_percentage() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 100"):
        make_record(attendance_percentage=Decimal("100.01"))
