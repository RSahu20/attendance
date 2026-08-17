from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from attendance.db.models.attendance import AttendanceRecord
from attendance.db.models.documents import DocumentVersion, ExtractedUnit
from attendance.domain.exports import ExportRecord, ExportRequest
from attendance.domain.security import AuthorizedScope


class ExportLimitExceeded(Exception):
    pass


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class AttendanceExportRepository:
    def select_authorized(
        self,
        session: Session,
        scope: AuthorizedScope,
        request: ExportRequest,
        *,
        max_records: int,
    ) -> list[ExportRecord]:
        predicates = [
            AttendanceRecord.product_id == scope.product_id,
            AttendanceRecord.tenant_id == scope.tenant_id,
            AttendanceRecord.entity_id == request.entity_id,
            AttendanceRecord.module == request.module,
            AttendanceRecord.classification <= int(request.classification),
            DocumentVersion.is_current.is_(True),
        ]
        if request.date_from:
            predicates.append(AttendanceRecord.attendance_date >= request.date_from)
        if request.date_to:
            predicates.append(AttendanceRecord.attendance_date <= request.date_to)
        if request.employee_id:
            predicates.append(AttendanceRecord.subject_external_id == request.employee_id)
        if request.status:
            predicates.append(AttendanceRecord.status == request.status.value)

        rows = session.execute(
            select(AttendanceRecord, DocumentVersion, ExtractedUnit)
            .join(DocumentVersion, DocumentVersion.id == AttendanceRecord.source_version_id)
            .join(ExtractedUnit, ExtractedUnit.id == AttendanceRecord.source_unit_id)
            .where(*predicates)
            .order_by(
                AttendanceRecord.attendance_date,
                AttendanceRecord.subject_external_id,
                AttendanceRecord.id,
            )
            .limit(max_records + 1)
        ).all()
        if len(rows) > max_records:
            raise ExportLimitExceeded

        records = []
        for attendance, version, unit in rows:
            locator = unit.source_locator or attendance.raw_row_metadata
            records.append(
                ExportRecord(
                    attendance_date=attendance.attendance_date,
                    employee_id=attendance.subject_external_id,
                    employee_name=attendance.subject_display_name,
                    department=attendance.course_or_group,
                    status=attendance.status,
                    check_in=attendance.check_in,
                    check_out=attendance.check_out,
                    total_hours=(
                        round(attendance.attended_minutes / 60, 4)
                        if attendance.attended_minutes is not None
                        else None
                    ),
                    attendance_percentage=(
                        float(attendance.attendance_percentage)
                        if attendance.attendance_percentage is not None
                        else None
                    ),
                    source_file=version.source_filename,
                    source_page=_optional_int(locator.get("page")),
                    source_sheet=locator.get("sheet"),
                    source_row=_optional_int(locator.get("row")),
                    source_record_id=attendance.source_record_key,
                    extraction_confidence=float(attendance.extraction_confidence),
                    review_status=attendance.review_status,
                )
            )
        return records
