from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from attendance.config import Settings, get_settings
from attendance.db.rls import set_authorization_context
from attendance.db.session import get_db
from attendance.domain.security import AuthorizedScope
from attendance.security.authentication import (
    AuthenticationError,
    Principal,
    decode_access_token,
)
from attendance.security.authorization import AuthorizationDenied, AuthorizationService

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return decode_access_token(credentials.credentials, settings)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_authorized_scope(
    product_id: Annotated[UUID, Header(alias="X-Product-ID")],
    tenant_id: Annotated[UUID, Header(alias="X-Tenant-ID")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    session: Annotated[Session, Depends(get_db)],
) -> AuthorizedScope:
    try:
        scope = AuthorizationService().resolve_scope(
            session,
            principal,
            product_id=product_id,
            tenant_id=tenant_id,
        )
    except AuthorizationDenied as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requested scope is unavailable",
        ) from exc
    set_authorization_context(session, scope)
    return scope
