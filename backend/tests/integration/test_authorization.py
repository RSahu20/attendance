from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from attendance.config import get_settings
from attendance.db.rls import set_authorization_context
from attendance.domain.security import ClassificationLevel
from attendance.main import app
from attendance.security.authentication import Principal
from attendance.security.authorization import AuthorizationDenied, AuthorizationService
from tests.integration.conftest import SecuritySeed


def make_token(subject: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": subject,
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


@pytest.mark.integration
def test_scope_resolution_denies_other_tenant(
    database_url: str, security_seed: SecuritySeed
) -> None:
    engine = create_engine(database_url)
    try:
        with Session(engine) as session, pytest.raises(AuthorizationDenied, match="unavailable"):
            AuthorizationService().resolve_scope(
                session,
                Principal(subject=security_seed.subject),
                product_id=security_seed.product_id,
                tenant_id=security_seed.tenant_b_id,
            )
    finally:
        engine.dispose()


@pytest.mark.integration
def test_rls_helper_preserves_indivisible_grants(
    database_url: str, security_seed: SecuritySeed
) -> None:
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            scope = AuthorizationService().resolve_scope(
                session,
                Principal(subject=security_seed.subject),
                product_id=security_seed.product_id,
                tenant_id=security_seed.tenant_a_id,
            )
            set_authorization_context(session, scope)
            high_allowed = session.scalar(
                text(
                    """
                    SELECT app_scope_allows(
                        :product_id, :tenant_id, :entity_id, 'attendance', :classification,
                        'attendance:read'
                    )
                    """
                ),
                {
                    "product_id": security_seed.product_id,
                    "tenant_id": security_seed.tenant_a_id,
                    "entity_id": security_seed.entity_high_id,
                    "classification": int(ClassificationLevel.CONFIDENTIAL),
                },
            )
            low_denied = session.scalar(
                text(
                    """
                    SELECT app_scope_allows(
                        :product_id, :tenant_id, :entity_id, 'attendance', :classification,
                        'attendance:read'
                    )
                    """
                ),
                {
                    "product_id": security_seed.product_id,
                    "tenant_id": security_seed.tenant_a_id,
                    "entity_id": security_seed.entity_low_id,
                    "classification": int(ClassificationLevel.CONFIDENTIAL),
                },
            )
    finally:
        engine.dispose()

    assert high_allowed is True
    assert low_denied is False


@pytest.mark.integration
def test_authorization_context_endpoint_is_tenant_scoped(
    security_seed: SecuritySeed,
) -> None:
    headers = {
        "Authorization": f"Bearer {make_token(security_seed.subject)}",
        "X-Product-ID": str(security_seed.product_id),
        "X-Tenant-ID": str(security_seed.tenant_a_id),
    }
    with TestClient(app) as client:
        allowed = client.get("/api/v1/auth/context", headers=headers)
        denied = client.get(
            "/api/v1/auth/context",
            headers={**headers, "X-Tenant-ID": str(security_seed.tenant_b_id)},
        )

    assert allowed.status_code == 200
    assert allowed.json()["tenant_id"] == str(security_seed.tenant_a_id)
    assert denied.status_code == 403
    assert denied.json() == {"detail": "Requested scope is unavailable"}
