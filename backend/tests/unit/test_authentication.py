from datetime import UTC, datetime, timedelta

import jwt
import pytest

from attendance.config import Settings
from attendance.security.authentication import AuthenticationError, decode_access_token


def make_settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:password@db/app",
        jwt_secret="unit-test-secret-with-at-least-32-bytes",
        jwt_issuer="test-issuer",
        jwt_audience="test-audience",
        app_env="test",
    )


def test_decode_access_token_accepts_valid_registered_claims() -> None:
    settings = make_settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "identity-subject",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )

    principal = decode_access_token(token, settings)

    assert principal.subject == "identity-subject"


def test_decode_access_token_rejects_wrong_audience() -> None:
    settings = make_settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "identity-subject",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "iss": settings.jwt_issuer,
            "aud": "wrong-audience",
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )

    with pytest.raises(AuthenticationError, match="Invalid access token"):
        decode_access_token(token, settings)
