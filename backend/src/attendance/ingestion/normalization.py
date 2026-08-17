from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from attendance.domain.attendance import (
    AttendanceStatus,
    CanonicalAttendanceRecord,
    ReviewStatus,
)
from attendance.domain.security import ClassificationLevel
from attendance.ingestion.types import ParsedUnit, RecordIssue


@dataclass(frozen=True)
class NormalizationContext:
    product_id: UUID
    tenant_id: UUID
    entity_id: UUID
    module: str
    classification: ClassificationLevel
    document_id: UUID
    document_version_id: UUID
    extracted_unit_id: UUID
    filename: str


@dataclass(frozen=True)
class NormalizationOutcome:
    record: CanonicalAttendanceRecord | None
    issue: RecordIssue | None


STATUS_MAP: dict[str, tuple[AttendanceStatus, str | None]] = {
    "present": (AttendanceStatus.PRESENT, None),
    "p": (AttendanceStatus.PRESENT, None),
    "absent": (AttendanceStatus.ABSENT, None),
    "a": (AttendanceStatus.ABSENT, None),
    "late": (AttendanceStatus.LATE, None),
    "partial": (AttendanceStatus.PARTIAL, None),
    "half day": (AttendanceStatus.PARTIAL, None),
    "half-day": (AttendanceStatus.PARTIAL, None),
    "excused": (AttendanceStatus.EXCUSED, None),
    "leave": (AttendanceStatus.EXCUSED, "status 'leave' mapped to excused"),
    "sick leave": (AttendanceStatus.EXCUSED, "status 'sick leave' mapped to excused"),
    "vacation": (AttendanceStatus.EXCUSED, "status 'vacation' mapped to excused"),
    "wfh": (AttendanceStatus.PRESENT, "status 'WFH' mapped to present; work mode retained"),
    "work from home": (
        AttendanceStatus.PRESENT,
        "status 'work from home' mapped to present; work mode retained",
    ),
}


def _empty_to_none(value: Any) -> Any | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return value


def _parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d %b %Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ValueError("attendance date is invalid")


def _parse_time(value: Any, attendance_date: date) -> datetime | None:
    value = _empty_to_none(value)
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, time):
        parsed = datetime.combine(attendance_date, value)
    else:
        text = str(value).strip()
        parsed_time: time | None = None
        for pattern in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p"):
            try:
                parsed_time = datetime.strptime(text, pattern).time()
                break
            except ValueError:
                continue
        if parsed_time is None:
            raise ValueError(f"time value '{text}' is invalid")
        parsed = datetime.combine(attendance_date, parsed_time)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _parse_decimal(value: Any, field_name: str) -> Decimal | None:
    value = _empty_to_none(value)
    if value is None:
        return None
    text = str(value).strip().replace("%", "")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} is invalid") from exc


def _parse_duration_minutes(value: Any) -> int | None:
    value = _empty_to_none(value)
    if value is None:
        return None
    text = str(value).strip()
    if ":" in text:
        hours, minutes = text.split(":", 1)
        result = int(hours) * 60 + int(minutes)
    else:
        result = int((_parse_decimal(value, "total hours") or Decimal(0)) * 60)
    if result < 0:
        raise ValueError("total hours cannot be negative")
    return result


class AttendanceNormalizer:
    def normalize(self, unit: ParsedUnit, context: NormalizationContext) -> NormalizationOutcome:
        if not unit.structured_data:
            return NormalizationOutcome(record=None, issue=None)
        data = unit.structured_data
        warnings: list[str] = []
        try:
            attendance_date = _parse_date(data.get("attendance_date"))
            employee_id = _empty_to_none(data.get("employee_id"))
            if employee_id is None:
                raise ValueError("employee identity is required")
            raw_status = str(_empty_to_none(data.get("status")) or "").strip()
            if not raw_status:
                raise ValueError("attendance status is required")
            status_entry = STATUS_MAP.get(raw_status.lower())
            review_status = unit.review_status
            if status_entry is None:
                status = AttendanceStatus.UNKNOWN
                warnings.append(f"unsupported status '{raw_status}' mapped to unknown")
                review_status = ReviewStatus.REVIEW_REQUIRED
            else:
                status, warning = status_entry
                if warning:
                    warnings.append(warning)

            check_in = _parse_time(data.get("check_in"), attendance_date)
            check_out = _parse_time(data.get("check_out"), attendance_date)
            if check_in and check_out and check_out < check_in:
                raise ValueError("check-out cannot precede check-in")
            percentage = _parse_decimal(data.get("attendance_percentage"), "percentage")
            if percentage is not None and not 0 <= percentage <= 100:
                raise ValueError("attendance percentage must be between 0 and 100")
            attended_minutes = _parse_duration_minutes(data.get("total_hours"))
            source_metadata = {
                **data,
                "source_file": context.filename,
                **unit.source_locator,
                "original_status": raw_status,
            }
            record = CanonicalAttendanceRecord(
                product_id=context.product_id,
                tenant_id=context.tenant_id,
                entity_id=context.entity_id,
                module=context.module,
                classification=context.classification,
                subject_external_id=str(employee_id).strip(),
                subject_display_name=(
                    str(data["employee_name"]).strip()
                    if _empty_to_none(data.get("employee_name")) is not None
                    else None
                ),
                attendance_date=attendance_date,
                course_or_group=(
                    str(data["department"]).strip()
                    if _empty_to_none(data.get("department")) is not None
                    else None
                ),
                status=status,
                check_in=check_in,
                check_out=check_out,
                attended_minutes=attended_minutes,
                attendance_percentage=percentage,
                source_document_id=context.document_id,
                source_version_id=context.document_version_id,
                source_unit_id=context.extracted_unit_id,
                source_record_key=unit.source_unit_key,
                raw_row_metadata=source_metadata,
                extraction_method=unit.extraction_method,
                extraction_confidence=unit.extraction_confidence,
                review_status=review_status,
                normalization_warnings=warnings,
            )
            return NormalizationOutcome(record=record, issue=None)
        except (ValueError, TypeError, ValidationError) as exc:
            return NormalizationOutcome(
                record=None,
                issue=RecordIssue(
                    source_unit_key=unit.source_unit_key,
                    code="normalization_invalid",
                    message=str(exc),
                    warnings=tuple(warnings),
                ),
            )
