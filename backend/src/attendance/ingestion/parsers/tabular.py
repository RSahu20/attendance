import re
from collections.abc import Sequence
from typing import Any

from attendance.domain.attendance import ExtractionMethod, ReviewStatus
from attendance.ingestion.types import ParsedUnit

ALIASES: dict[str, set[str]] = {
    "attendance_date": {"date", "attendance_date", "attendance date"},
    "employee_id": {"employee_id", "emp_id", "employee code", "employee_code", "id"},
    "employee_name": {"employee_name", "name", "employee"},
    "status": {"status", "attendance", "attendance_status"},
    "department": {"department", "dept", "team"},
    "check_in": {"check_in", "check-in", "in_time"},
    "check_out": {"check_out", "check-out", "out_time"},
    "total_hours": {"total_hours", "hours", "worked_hours"},
    "attendance_percentage": {"attendance_percentage", "attendance %", "percentage"},
}


def normalize_header(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"\s+", " ", text.replace("_", " ")).strip()


ALIAS_LOOKUP = {
    normalize_header(alias): canonical
    for canonical, aliases in ALIASES.items()
    for alias in aliases
}


class AttendanceHeaderNotFound(ValueError):
    """Raised when tabular content is readable but has no attendance header."""


def canonical_header(value: Any) -> str | None:
    return ALIAS_LOOKUP.get(normalize_header(value))


def detect_header(
    rows: Sequence[Sequence[Any]], scan_limit: int = 20
) -> tuple[int, dict[int, str]]:
    best: tuple[int, int, dict[int, str]] | None = None
    for row_index, row in enumerate(rows[:scan_limit]):
        mapping = {
            column_index: canonical
            for column_index, value in enumerate(row)
            if (canonical := canonical_header(value)) is not None
        }
        unique_fields = set(mapping.values())
        score = len(unique_fields)
        required = "attendance_date" in unique_fields and "status" in unique_fields
        identity = "employee_id" in unique_fields or "employee_name" in unique_fields
        if required and identity and score >= 3 and (best is None or score > best[0]):
            best = (score, row_index, mapping)
    if best is None:
        raise AttendanceHeaderNotFound("No attendance header row was detected")
    return best[1], best[2]


def table_units(
    rows: Sequence[Sequence[Any]],
    *,
    filename: str,
    location: dict[str, Any],
    key_prefix: str,
    method: ExtractionMethod,
    confidence: float = 1.0,
    review_status: ReviewStatus = ReviewStatus.ACCEPTED,
) -> list[ParsedUnit]:
    header_index, mapping = detect_header(rows)
    units: list[ParsedUnit] = []
    for row_index, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if not any(value is not None and str(value).strip() for value in row):
            continue
        data = {
            canonical: row[column_index]
            for column_index, canonical in mapping.items()
            if column_index < len(row) and row[column_index] is not None
        }
        locator = {"file": filename, **location, "row": row_index}
        units.append(
            ParsedUnit(
                source_unit_key=f"{key_prefix}:row:{row_index}",
                unit_type="attendance_row",
                source_locator=locator,
                raw_text=" | ".join(str(value or "") for value in row),
                structured_data=data,
                extraction_method=method,
                extraction_confidence=confidence,
                review_status=review_status,
            )
        )
    return units


def rows_from_text(text: str) -> list[list[str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    if any("," in line for line in lines):
        import csv

        return list(csv.reader(lines, strict=True))
    delimiter = "\t" if any("\t" in line for line in lines) else "|"
    if delimiter == "|" and not any("|" in line for line in lines):
        return [re.split(r"\s{2,}", line) for line in lines]
    return [[cell.strip() for cell in line.split(delimiter)] for line in lines]
