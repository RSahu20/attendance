from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from attendance.db.session import get_db

router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    status: Literal["alive"]


class ReadinessResponse(BaseModel):
    status: Literal["ready"]
    checks: dict[str, Literal["available"]]
    pgvector_version: str


@router.get("/live", response_model=LivenessResponse)
def liveness() -> LivenessResponse:
    return LivenessResponse(status="alive")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Dependency unavailable"}},
)
def readiness(db: Annotated[Session, Depends(get_db)]) -> ReadinessResponse | JSONResponse:
    try:
        db.execute(text("SELECT 1")).scalar_one()
    except SQLAlchemyError:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "checks": {"postgresql": "unavailable", "pgvector": "unavailable"},
            },
        )

    try:
        vector_version = db.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one_or_none()
    except SQLAlchemyError:
        vector_version = None

    if vector_version is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "checks": {"postgresql": "available", "pgvector": "unavailable"},
            },
        )

    return ReadinessResponse(
        status="ready",
        checks={"postgresql": "available", "pgvector": "available"},
        pgvector_version=str(vector_version),
    )
