from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from attendance.audit.service import append_audit_event
from attendance.db.models.exports import ExportJob
from attendance.db.rls import set_authorization_context
from attendance.domain.exports import ExportMetadata, ExportRequest, ExportStatus
from attendance.domain.security import AuthorizedScope, ClassificationLevel
from attendance.exports.renderers import RENDERERS
from attendance.exports.repository import AttendanceExportRepository, ExportLimitExceeded
from attendance.providers.storage.base import StorageProvider


class ExportNotFound(Exception):
    pass


class ExportExpired(Exception):
    pass


class ExportUnavailable(Exception):
    pass


class ExportService:
    def __init__(
        self,
        storage: StorageProvider,
        *,
        ttl_seconds: int,
        max_records: int,
    ) -> None:
        self.storage = storage
        self.ttl_seconds = ttl_seconds
        self.max_records = max_records
        self.repository = AttendanceExportRepository()

    def create(
        self,
        session: Session,
        scope: AuthorizedScope,
        request: ExportRequest,
    ) -> ExportJob:
        self.cleanup_expired(session, scope)
        set_authorization_context(session, scope)
        now = datetime.now(UTC)
        job = ExportJob(
            id=uuid4(),
            request_id=uuid4(),
            product_id=scope.product_id,
            tenant_id=scope.tenant_id,
            entity_id=request.entity_id,
            module=request.module,
            classification=int(request.classification),
            requested_by_user_id=scope.user_id,
            format=request.format.value,
            dataset=request.dataset,
            filters=request.model_dump(
                mode="json",
                exclude={"format", "dataset", "entity_id", "module", "classification"},
                exclude_none=True,
            ),
            status=ExportStatus.REQUESTED.value,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
        )
        session.add(job)
        self._audit(session, scope, job, request, action="export.requested", outcome="requested")
        session.commit()
        set_authorization_context(session, scope)

        storage_key: str | None = None
        try:
            records = self.repository.select_authorized(
                session,
                scope,
                request,
                max_records=self.max_records,
            )
            metadata = ExportMetadata(
                export_id=job.id,
                exported_at=now,
                product_id=scope.product_id,
                tenant_id=scope.tenant_id,
                entity_id=request.entity_id,
                module=request.module,
                classification=int(request.classification),
                filters=job.filters,
            )
            artifact = RENDERERS[request.format].render(records, metadata)
            filename = f"attendance-export-{job.id}.{artifact.extension}"
            storage_key = f"exports/{scope.tenant_id}/{job.id}/{filename}"
            self.storage.store(storage_key, artifact.content)

            job.status = ExportStatus.COMPLETED.value
            job.storage_key = storage_key
            job.filename = filename
            job.media_type = artifact.media_type
            job.record_count = len(records)
            job.byte_size = len(artifact.content)
            job.completed_at = datetime.now(UTC)
            job.updated_at = job.completed_at
            self._audit(
                session,
                scope,
                job,
                request,
                action="export.completed",
                outcome="completed",
            )
            session.commit()
        except Exception as exc:
            session.rollback()
            if storage_key:
                self.storage.delete(storage_key)
            set_authorization_context(session, scope)
            failed = session.get(ExportJob, job.id)
            if failed is None:
                raise
            failed.status = ExportStatus.FAILED.value
            failed.failure_code = (
                "EXPORT_RECORD_LIMIT_EXCEEDED"
                if isinstance(exc, ExportLimitExceeded)
                else "EXPORT_GENERATION_FAILED"
            )
            failed.updated_at = datetime.now(UTC)
            self._audit(
                session,
                scope,
                failed,
                request,
                action="export.failed",
                outcome="failed",
            )
            session.commit()
            job = failed
        set_authorization_context(session, scope)
        session.refresh(job)
        return job

    def get_owned(
        self,
        session: Session,
        scope: AuthorizedScope,
        export_id: UUID,
    ) -> ExportJob:
        set_authorization_context(session, scope)
        job = session.scalar(
            select(ExportJob).where(
                ExportJob.id == export_id,
                ExportJob.product_id == scope.product_id,
                ExportJob.tenant_id == scope.tenant_id,
                ExportJob.requested_by_user_id == scope.user_id,
            )
        )
        if job is None or not scope.permits(
            "attendance:export",
            entity_id=job.entity_id,
            module=job.module,
            classification=ClassificationLevel(job.classification),
        ):
            raise ExportNotFound
        return job

    def download(
        self,
        session: Session,
        scope: AuthorizedScope,
        export_id: UUID,
    ) -> tuple[ExportJob, bytes]:
        self.cleanup_expired(session, scope)
        job = self.get_owned(session, scope, export_id)
        if not all(
            scope.permits(
                permission,
                entity_id=job.entity_id,
                module=job.module,
                classification=ClassificationLevel(job.classification),
            )
            for permission in ("attendance:read", "attendance:export", "audit:write")
        ):
            raise ExportNotFound
        if job.status == ExportStatus.EXPIRED.value or job.expires_at <= datetime.now(UTC):
            raise ExportExpired
        if job.status != ExportStatus.COMPLETED.value or not job.storage_key:
            raise ExportUnavailable
        try:
            content = self.storage.read(job.storage_key)
        except FileNotFoundError as exc:
            raise ExportUnavailable from exc
        set_authorization_context(session, scope)
        append_audit_event(
            session,
            scope,
            request_id=job.request_id,
            action="export.downloaded",
            resource_type="export",
            resource_id=str(job.id),
            outcome="downloaded",
            entity_id=job.entity_id,
            module=job.module,
            classification=ClassificationLevel(job.classification),
            metadata=self._audit_metadata(job, outcome="downloaded"),
        )
        session.commit()
        set_authorization_context(session, scope)
        session.refresh(job)
        return job, content

    def cleanup_expired(self, session: Session, scope: AuthorizedScope) -> int:
        set_authorization_context(session, scope)
        jobs = session.scalars(
            select(ExportJob).where(
                ExportJob.product_id == scope.product_id,
                ExportJob.tenant_id == scope.tenant_id,
                ExportJob.requested_by_user_id == scope.user_id,
                ExportJob.status == ExportStatus.COMPLETED.value,
                ExportJob.expires_at <= datetime.now(UTC),
            )
        ).all()
        for job in jobs:
            if job.storage_key:
                self.storage.delete(job.storage_key)
            job.storage_key = None
            job.status = ExportStatus.EXPIRED.value
            job.updated_at = datetime.now(UTC)
        if jobs:
            session.commit()
        return len(jobs)

    def _audit(
        self,
        session: Session,
        scope: AuthorizedScope,
        job: ExportJob,
        request: ExportRequest,
        *,
        action: str,
        outcome: str,
    ) -> None:
        append_audit_event(
            session,
            scope,
            request_id=job.request_id,
            action=action,
            resource_type="export",
            resource_id=str(job.id),
            outcome=outcome,
            entity_id=request.entity_id,
            module=request.module,
            classification=request.classification,
            metadata=self._audit_metadata(job, outcome=outcome),
        )

    def _audit_metadata(self, job: ExportJob, *, outcome: str) -> dict[str, str]:
        return {
            "request_id": str(job.request_id),
            "export_id": str(job.id),
            "format": job.format,
            "product_id": str(job.product_id),
            "tenant_id": str(job.tenant_id),
            "module": job.module,
            "outcome": outcome,
        }
