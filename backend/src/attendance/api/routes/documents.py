from datetime import datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from attendance.api.dependencies import get_authorized_scope
from attendance.config import Settings, get_settings
from attendance.db.models.documents import DocumentVersion, IngestionJob
from attendance.db.session import get_db
from attendance.domain.security import AuthorizedScope, ClassificationLevel
from attendance.ingestion.checksum import sha256_hex
from attendance.ingestion.normalization import AttendanceNormalizer
from attendance.ingestion.parsers.registry import ParserRegistry
from attendance.ingestion.service import IngestionCommand, IngestionService
from attendance.providers.ocr.tesseract import TesseractProvider
from attendance.providers.storage.local import LocalStorageProvider

router = APIRouter(prefix="/api/v1", tags=["ingestion"])


class UploadResponse(BaseModel):
    job_id: UUID
    document_id: UUID
    document_version_id: UUID
    checksum: str
    status: str
    idempotent: bool


class IngestionJobResponse(BaseModel):
    job_id: UUID
    status: str
    current_stage: str
    document_id: UUID
    document_version_id: UUID
    extracted_unit_count: int
    normalized_record_count: int
    review_required_count: int
    error_count: int
    errors: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


def _require_ingestion_access(
    scope: AuthorizedScope,
    *,
    entity_id: UUID,
    module: str,
    classification: ClassificationLevel,
) -> None:
    required = ("document:write", "attendance:write", "audit:write")
    if not all(
        scope.permits(
            permission,
            entity_id=entity_id,
            module=module,
            classification=classification,
        )
        for permission in required
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requested scope is unavailable",
        )


async def _read_upload(file: UploadFile, max_bytes: int) -> bytes:
    content = bytearray()
    while chunk := await file.read(1024 * 1024):
        content.extend(chunk)
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="The uploaded file is too large",
            )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The uploaded file is empty",
        )
    return bytes(content)


@router.post("/documents", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: Annotated[UploadFile, File()],
    entity_id: Annotated[UUID, Form()],
    module: Annotated[str, Form(min_length=1, max_length=64)],
    classification: Annotated[ClassificationLevel, Form()],
    scope: Annotated[AuthorizedScope, Depends(get_authorized_scope)],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    logical_name: Annotated[str | None, Form(max_length=255)] = None,
) -> UploadResponse:
    _require_ingestion_access(
        scope,
        entity_id=entity_id,
        module=module,
        classification=classification,
    )
    raw_filename = file.filename or ""
    filename = Path(raw_filename).name
    if not filename or filename in {".", ".."}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A valid filename is required",
        )
    resolved_logical_name = (logical_name or Path(filename).stem).strip()
    if not resolved_logical_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A logical document name is required",
        )
    content = await _read_upload(file, settings.max_upload_bytes)
    service = IngestionService(
        storage=LocalStorageProvider(settings.storage_root),
        parsers=ParserRegistry(TesseractProvider(), settings.ocr_confidence_threshold),
        normalizer=AttendanceNormalizer(),
    )
    result = service.ingest(
        session,
        scope,
        IngestionCommand(
            filename=filename,
            logical_name=resolved_logical_name,
            media_type=file.content_type or "application/octet-stream",
            content=content,
            checksum=sha256_hex(content),
            entity_id=entity_id,
            module=module,
            classification=classification,
        ),
    )
    return UploadResponse(**result.__dict__)


@router.get("/ingestion-jobs/{job_id}", response_model=IngestionJobResponse)
def get_ingestion_job(
    job_id: UUID,
    scope: Annotated[AuthorizedScope, Depends(get_authorized_scope)],
    session: Annotated[Session, Depends(get_db)],
) -> IngestionJobResponse:
    row = session.execute(
        select(IngestionJob, DocumentVersion.document_id)
        .join(DocumentVersion, DocumentVersion.id == IngestionJob.document_version_id)
        .where(IngestionJob.id == job_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion job is unavailable",
        )
    job, document_id = row
    if not scope.permits(
        "document:read",
        entity_id=job.entity_id,
        module=job.module,
        classification=ClassificationLevel(job.classification),
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion job is unavailable",
        )
    errors = job.error_summary.get("errors", [])
    return IngestionJobResponse(
        job_id=job.id,
        status=job.status,
        current_stage=job.current_stage,
        document_id=document_id,
        document_version_id=job.document_version_id,
        extracted_unit_count=job.processed_units,
        normalized_record_count=job.accepted_records,
        review_required_count=job.review_records,
        error_count=job.error_count,
        errors=errors if isinstance(errors, list) else [],
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
