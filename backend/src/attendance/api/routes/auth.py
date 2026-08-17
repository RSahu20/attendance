from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from attendance.api.dependencies import get_authorized_scope
from attendance.domain.security import AuthorizedScope, ClassificationLevel

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


class GrantResponse(BaseModel):
    role_id: UUID
    entity_id: UUID | None
    module: str | None
    classification_ceiling: ClassificationLevel
    permissions: list[str]


class AuthorizationContextResponse(BaseModel):
    user_id: UUID
    product_id: UUID
    tenant_id: UUID
    grants: list[GrantResponse]


@router.get("/context", response_model=AuthorizationContextResponse)
def authorization_context(
    scope: Annotated[AuthorizedScope, Depends(get_authorized_scope)],
) -> AuthorizationContextResponse:
    if not scope.has_permission_anywhere("security:context"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requested scope is unavailable",
        )
    return AuthorizationContextResponse(
        user_id=scope.user_id,
        product_id=scope.product_id,
        tenant_id=scope.tenant_id,
        grants=[
            GrantResponse(
                role_id=grant.role_id,
                entity_id=grant.entity_id,
                module=grant.module,
                classification_ceiling=grant.classification_ceiling,
                permissions=sorted(grant.permissions),
            )
            for grant in scope.grants
        ],
    )
