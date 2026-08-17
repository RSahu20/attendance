from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from attendance.audit.service import append_audit_event
from attendance.db.models.attendance import AttendanceRecord
from attendance.db.models.documents import (
    Document,
    DocumentChunk,
    DocumentVersion,
    ExtractedUnit,
    IngestionJob,
)
from attendance.db.rls import set_authorization_context
from attendance.domain.attendance import ReviewStatus
from attendance.domain.documents import IngestionStage
from attendance.domain.security import AuthorizedScope, ClassificationLevel
from attendance.ingestion.chunking import DocumentChunker
from attendance.ingestion.normalization import AttendanceNormalizer, NormalizationContext
from attendance.ingestion.parsers.registry import ParserRegistry
from attendance.ingestion.types import IngestionError, RecordIssue
from attendance.providers.storage.base import StorageProvider


@dataclass(frozen=True)
class IngestionCommand:
    filename: str
    logical_name: str
    media_type: str
    content: bytes
    checksum: str
    entity_id: UUID
    module: str
    classification: ClassificationLevel


@dataclass(frozen=True)
class IngestionResult:
    job_id: UUID
    document_id: UUID
    document_version_id: UUID
    checksum: str
    status: str
    idempotent: bool = False


class IngestionService:
    def __init__(
        self,
        storage: StorageProvider,
        parsers: ParserRegistry,
        normalizer: AttendanceNormalizer | None = None,
        chunker: DocumentChunker | None = None,
    ) -> None:
        self.storage = storage
        self.parsers = parsers
        self.normalizer = normalizer or AttendanceNormalizer()
        self.chunker = chunker or DocumentChunker()

    def ingest(
        self, session: Session, scope: AuthorizedScope, command: IngestionCommand
    ) -> IngestionResult:
        set_authorization_context(session, scope)
        document, version, job, duplicate = self._create_or_resolve_version(session, scope, command)
        set_authorization_context(session, scope)
        document_id = document.id
        version_id = version.id
        job_id = job.id
        storage_key = version.storage_key
        if duplicate:
            duplicate_status = job.status
            self._audit(
                session,
                scope,
                action="upload.accepted",
                outcome="idempotent",
                command=command,
                resource_id=str(version_id),
                metadata={"checksum": command.checksum, "job_id": str(job_id)},
            )
            session.commit()
            return IngestionResult(
                job_id=job_id,
                document_id=document_id,
                document_version_id=version_id,
                checksum=command.checksum,
                status=duplicate_status,
                idempotent=True,
            )

        try:
            self._transition(session, scope, job, IngestionStage.VALIDATING)
            parser = self.parsers.resolve(command.filename)
            version.parser_name = parser.name
            version.parser_version = parser.version

            self._transition(session, scope, job, IngestionStage.STORING)
            self.storage.store(storage_key, command.content)

            self._transition(session, scope, job, IngestionStage.EXTRACTING)
            parsed_units = parser.parse(command.content, command.filename)
            if not parsed_units:
                raise IngestionError("no_content", "The file contains no extractable content")

            self._transition(session, scope, job, IngestionStage.NORMALIZING)
            issues: list[RecordIssue] = []
            normalized_count = 0
            review_count = 0
            extracted_units: list[ExtractedUnit] = []
            pending_chunks: list[DocumentChunk] = []
            self._transition(session, scope, job, IngestionStage.PERSISTING)
            for parsed in parsed_units:
                extracted = ExtractedUnit(
                    document_version_id=version_id,
                    product_id=scope.product_id,
                    tenant_id=scope.tenant_id,
                    entity_id=command.entity_id,
                    module=command.module,
                    classification=int(command.classification),
                    source_unit_key=parsed.source_unit_key,
                    unit_type=parsed.unit_type,
                    source_locator=parsed.source_locator,
                    raw_text=parsed.raw_text,
                    structured_data=parsed.structured_data,
                    extraction_method=parsed.extraction_method.value,
                    extraction_confidence=parsed.extraction_confidence,
                    review_status=parsed.review_status.value,
                )
                session.add(extracted)
                session.flush()
                extracted_units.append(extracted)
                outcome = self.normalizer.normalize(
                    parsed,
                    NormalizationContext(
                        product_id=scope.product_id,
                        tenant_id=scope.tenant_id,
                        entity_id=command.entity_id,
                        module=command.module,
                        classification=command.classification,
                        document_id=document_id,
                        document_version_id=version_id,
                        extracted_unit_id=extracted.id,
                        filename=command.filename,
                    ),
                )
                if outcome.issue:
                    issues.append(outcome.issue)
                    extracted.review_status = ReviewStatus.REJECTED.value
                if outcome.record:
                    session.add(self._attendance_row(outcome.record.model_dump()))
                    normalized_count += 1
                    if outcome.record.review_status == ReviewStatus.REVIEW_REQUIRED:
                        review_count += 1
                for draft in self.chunker.chunk(parsed):
                    pending_chunks.append(
                        DocumentChunk(
                            document_version_id=version_id,
                            extracted_unit_id=extracted.id,
                            product_id=scope.product_id,
                            tenant_id=scope.tenant_id,
                            entity_id=command.entity_id,
                            module=command.module,
                            classification=int(command.classification),
                            chunk_key=draft.chunk_key,
                            content=draft.content,
                            source_locator=draft.source_locator,
                            token_count=draft.token_count,
                        )
                    )

            if normalized_count == 0:
                issues.append(
                    RecordIssue(
                        source_unit_key="document",
                        code="no_attendance_data_detected",
                        message=(
                            "The file is readable, but no canonical attendance records "
                            "were detected"
                        ),
                    )
                )
                for extracted in extracted_units:
                    if extracted.review_status != ReviewStatus.REJECTED.value:
                        extracted.review_status = ReviewStatus.REVIEW_REQUIRED.value
            else:
                session.add_all(pending_chunks)

            job.current_stage = IngestionStage.INDEXING.value
            job.processed_units = len(parsed_units)
            job.accepted_records = normalized_count
            job.review_records = review_count + len(issues)
            job.error_count = len(issues)
            job.error_summary = {"errors": [asdict(issue) for issue in issues]}
            final_review = job.review_records > 0
            now = datetime.now(UTC)
            job.status = "review_required" if final_review else "completed"
            job.current_stage = (
                IngestionStage.REVIEW_REQUIRED.value
                if final_review
                else IngestionStage.COMPLETED.value
            )
            job.completed_at = now
            job.updated_at = now
            version.status = "review_required" if final_review else "ready"
            self._audit(
                session,
                scope,
                action="ingestion.completed",
                outcome=job.status,
                command=command,
                resource_id=str(job_id),
                metadata={
                    "document_version_id": str(version_id),
                    "extracted_units": len(parsed_units),
                    "normalized_records": normalized_count,
                    "review_required": job.review_records,
                    "errors": len(issues),
                },
            )
            final_status = job.status
            session.commit()
            return IngestionResult(
                job_id=job_id,
                document_id=document_id,
                document_version_id=version_id,
                checksum=command.checksum,
                status=final_status,
            )
        except Exception as exc:
            session.rollback()
            return self._record_failure(
                session, scope, command, document_id, version_id, job_id, exc
            )

    def _create_or_resolve_version(
        self, session: Session, scope: AuthorizedScope, command: IngestionCommand
    ) -> tuple[Document, DocumentVersion, IngestionJob, bool]:
        lock_key = ":".join(
            (
                str(scope.product_id),
                str(scope.tenant_id),
                str(command.entity_id),
                command.module,
                str(int(command.classification)),
                command.logical_name,
            )
        )
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": lock_key},
        )
        document = session.scalar(
            select(Document).where(
                Document.product_id == scope.product_id,
                Document.tenant_id == scope.tenant_id,
                Document.entity_id == command.entity_id,
                Document.module == command.module,
                Document.classification == int(command.classification),
                Document.logical_name == command.logical_name,
            )
        )
        if document is None:
            document = Document(
                product_id=scope.product_id,
                tenant_id=scope.tenant_id,
                entity_id=command.entity_id,
                module=command.module,
                classification=int(command.classification),
                logical_name=command.logical_name,
                created_by_user_id=scope.user_id,
            )
            session.add(document)
            session.flush()

        existing_version = session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.sha256 == command.checksum,
            )
        )
        if existing_version is not None:
            existing_job = session.scalar(
                select(IngestionJob)
                .where(IngestionJob.document_version_id == existing_version.id)
                .order_by(IngestionJob.created_at.desc())
            )
            if existing_job is not None:
                return document, existing_version, existing_job, True

        latest_number = session.scalar(
            select(DocumentVersion.version_number)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_number.desc())
            .limit(1)
        )
        current = session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.is_current.is_(True),
            )
        )
        if current is not None:
            current.is_current = False
            current.status = "superseded"
        version = existing_version or DocumentVersion(
            id=uuid4(),
            document_id=document.id,
            product_id=scope.product_id,
            tenant_id=scope.tenant_id,
            entity_id=command.entity_id,
            module=command.module,
            classification=int(command.classification),
            version_number=(latest_number or 0) + 1,
            sha256=command.checksum,
            source_filename=command.filename,
            media_type=command.media_type,
            byte_size=len(command.content),
            storage_key=self._storage_key(scope, command, document.id),
            status="pending",
            is_current=True,
            version_metadata={"logical_name": command.logical_name},
            created_by_user_id=scope.user_id,
        )
        if existing_version is None:
            session.add(version)
            session.flush()
        job = IngestionJob(
            document_version_id=version.id,
            product_id=scope.product_id,
            tenant_id=scope.tenant_id,
            entity_id=command.entity_id,
            module=command.module,
            classification=int(command.classification),
            status="received",
            current_stage=IngestionStage.RECEIVED.value,
            requested_by_user_id=scope.user_id,
            started_at=datetime.now(UTC),
        )
        session.add(job)
        session.flush()
        self._audit(
            session,
            scope,
            action="document.version_created",
            outcome="accepted",
            command=command,
            resource_id=str(version.id),
            metadata={"checksum": command.checksum, "version_number": version.version_number},
        )
        self._audit(
            session,
            scope,
            action="upload.accepted",
            outcome="accepted",
            command=command,
            resource_id=str(document.id),
            metadata={"job_id": str(job.id), "document_version_id": str(version.id)},
        )
        session.commit()
        return document, version, job, False

    def _transition(
        self, session: Session, scope: AuthorizedScope, job: IngestionJob, stage: IngestionStage
    ) -> None:
        set_authorization_context(session, scope)
        job.status = "running"
        job.current_stage = stage.value
        job.updated_at = datetime.now(UTC)
        session.commit()
        set_authorization_context(session, scope)

    def _record_failure(
        self,
        session: Session,
        scope: AuthorizedScope,
        command: IngestionCommand,
        document_id: UUID,
        version_id: UUID,
        job_id: UUID,
        exc: Exception,
    ) -> IngestionResult:
        set_authorization_context(session, scope)
        job = session.get(IngestionJob, job_id)
        version = session.get(DocumentVersion, version_id)
        if isinstance(exc, IngestionError):
            code, message = exc.code, exc.safe_message
        else:
            code, message = "ingestion_failure", "The file could not be ingested"
        now = datetime.now(UTC)
        if job is not None:
            job.status = "failed"
            job.current_stage = IngestionStage.FAILED.value
            job.error_count = 1
            job.error_summary = {"errors": [{"code": code, "message": message}]}
            job.completed_at = now
            job.updated_at = now
        if version is not None:
            version.status = "failed"
            version.failure_code = code
            version.failure_detail = message
        self._audit(
            session,
            scope,
            action="upload.rejected",
            outcome="failed",
            command=command,
            resource_id=str(version_id),
            metadata={"job_id": str(job_id), "error_code": code},
        )
        self._audit(
            session,
            scope,
            action="ingestion.failed",
            outcome="failed",
            command=command,
            resource_id=str(job_id),
            metadata={"error_code": code},
        )
        session.commit()
        return IngestionResult(
            job_id=job_id,
            document_id=document_id,
            document_version_id=version_id,
            checksum=command.checksum,
            status="failed",
        )

    @staticmethod
    def _attendance_row(values: dict[str, Any]) -> AttendanceRecord:
        values["classification"] = int(values["classification"])
        values["status"] = values["status"].value
        values["extraction_method"] = values["extraction_method"].value
        values["review_status"] = values["review_status"].value
        return AttendanceRecord(**values)

    @staticmethod
    def _storage_key(scope: AuthorizedScope, command: IngestionCommand, document_id: UUID) -> str:
        suffix = Path(command.filename).suffix.lower()
        return f"{scope.product_id}/{scope.tenant_id}/{document_id}/{command.checksum}{suffix}"

    @staticmethod
    def _audit(
        session: Session,
        scope: AuthorizedScope,
        *,
        action: str,
        outcome: str,
        command: IngestionCommand,
        resource_id: str,
        metadata: dict[str, Any],
    ) -> None:
        append_audit_event(
            session,
            scope,
            action=action,
            resource_type="document_ingestion",
            resource_id=resource_id,
            outcome=outcome,
            entity_id=command.entity_id,
            module=command.module,
            classification=command.classification,
            metadata=metadata,
        )
