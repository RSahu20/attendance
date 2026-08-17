from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from attendance.api.dependencies import get_authorized_scope
from attendance.config import Settings, get_settings
from attendance.db.models.exports import ExportJob
from attendance.db.session import get_db
from attendance.domain.exports import ExportJobResponse, ExportRequest
from attendance.domain.security import AuthorizedScope
from attendance.exports.service import (
    ExportExpired,
    ExportNotFound,
    ExportService,
    ExportUnavailable,
)
from attendance.providers.storage.base import StorageProvider
from attendance.providers.storage.local import LocalStorageProvider

router = APIRouter(prefix="/api/v1", tags=["exports"])


def get_export_storage(
    settings: Annotated[Settings, Depends(get_settings)],
) -> StorageProvider:
    return LocalStorageProvider(settings.storage_root)


def _service(settings: Settings, storage: StorageProvider) -> ExportService:
    return ExportService(
        storage,
        ttl_seconds=settings.export_ttl_seconds,
        max_records=settings.export_max_records,
    )


def _require_create_access(scope: AuthorizedScope, request: ExportRequest) -> None:
    if not all(
        scope.permits(
            permission,
            entity_id=request.entity_id,
            module=request.module,
            classification=request.classification,
        )
        for permission in ("attendance:read", "attendance:export", "audit:write")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requested scope is unavailable",
        )


def _response(job: ExportJob) -> ExportJobResponse:
    return ExportJobResponse(
        export_id=job.id,
        status=job.status,
        format=job.format,
        created_at=job.created_at,
        expires_at=job.expires_at,
        record_count=job.record_count,
        error_code=job.failure_code,
    )


@router.post("/exports", response_model=ExportJobResponse, status_code=status.HTTP_201_CREATED)
def create_export(
    request: ExportRequest,
    scope: Annotated[AuthorizedScope, Depends(get_authorized_scope)],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[StorageProvider, Depends(get_export_storage)],
) -> ExportJobResponse:
    _require_create_access(scope, request)
    return _response(_service(settings, storage).create(session, scope, request))


@router.get("/exports/{export_id}", response_model=ExportJobResponse)
def get_export(
    export_id: UUID,
    scope: Annotated[AuthorizedScope, Depends(get_authorized_scope)],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[StorageProvider, Depends(get_export_storage)],
) -> ExportJobResponse:
    service = _service(settings, storage)
    service.cleanup_expired(session, scope)
    try:
        return _response(service.get_owned(session, scope, export_id))
    except ExportNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export is unavailable",
        ) from exc


@router.get("/exports/{export_id}/download")
def download_export(
    export_id: UUID,
    scope: Annotated[AuthorizedScope, Depends(get_authorized_scope)],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    storage: Annotated[StorageProvider, Depends(get_export_storage)],
) -> Response:
    try:
        job, content = _service(settings, storage).download(session, scope, export_id)
    except ExportNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export is unavailable",
        ) from exc
    except ExportExpired as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Export has expired",
        ) from exc
    except ExportUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Export is not available for download",
        ) from exc
    return Response(
        content=content,
        media_type=job.media_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{job.filename}"'},
    )
