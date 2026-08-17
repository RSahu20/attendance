from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from attendance.db.models.attendance import AttendanceRecord
from attendance.db.models.documents import DocumentVersion
from attendance.domain.retrieval import QueryFilters, StructuredMetric
from attendance.domain.security import AuthorizedScope, ClassificationLevel


class StructuredRetriever:
    def retrieve(
        self,
        session: Session,
        scope: AuthorizedScope,
        *,
        entity_id: Any,
        module: str,
        classification: ClassificationLevel,
        metric: StructuredMetric,
        filters: QueryFilters,
    ) -> dict[str, Any]:
        predicates = [
            AttendanceRecord.product_id == scope.product_id,
            AttendanceRecord.tenant_id == scope.tenant_id,
            AttendanceRecord.entity_id == entity_id,
            AttendanceRecord.module == module,
            AttendanceRecord.classification <= int(classification),
            DocumentVersion.is_current.is_(True),
        ]
        if filters.date_from:
            predicates.append(AttendanceRecord.attendance_date >= filters.date_from)
        if filters.date_to:
            predicates.append(AttendanceRecord.attendance_date <= filters.date_to)
        if filters.employee_id:
            predicates.append(AttendanceRecord.subject_external_id == filters.employee_id)
        if filters.department:
            predicates.append(AttendanceRecord.course_or_group == filters.department)
        if filters.status:
            predicates.append(AttendanceRecord.status == filters.status.value)

        base_join = AttendanceRecord.source_version_id == DocumentVersion.id
        if metric == StructuredMetric.STATUS_BREAKDOWN:
            rows = session.execute(
                select(AttendanceRecord.status, func.count(AttendanceRecord.id))
                .join(DocumentVersion, base_join)
                .where(*predicates)
                .group_by(AttendanceRecord.status)
                .order_by(AttendanceRecord.status)
            ).all()
            return {"metric": metric.value, "value": {status: count for status, count in rows}}

        expression = {
            StructuredMetric.COUNT: func.count(AttendanceRecord.id),
            StructuredMetric.AVERAGE_PERCENTAGE: func.avg(AttendanceRecord.attendance_percentage),
            StructuredMetric.TOTAL_HOURS: func.sum(AttendanceRecord.attended_minutes) / 60.0,
            StructuredMetric.HIGHEST_PERCENTAGE: func.max(AttendanceRecord.attendance_percentage),
            StructuredMetric.LOWEST_PERCENTAGE: func.min(AttendanceRecord.attendance_percentage),
        }[metric]
        value = session.scalar(
            select(expression)
            .select_from(AttendanceRecord)
            .join(DocumentVersion, base_join)
            .where(*predicates)
        )
        return {"metric": metric.value, "value": float(value) if value is not None else None}
