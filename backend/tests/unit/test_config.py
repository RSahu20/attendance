import pytest
from pydantic import ValidationError

from attendance.config import Settings


def test_configuration_loads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:password@db:5432/app")
    monkeypatch.setenv("JWT_SECRET", "test-secret-with-at-least-32-bytes")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173,https://example.test")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.app_env == "test"
    assert settings.database_url.endswith("@db:5432/app")
    assert settings.jwt_secret.get_secret_value() == "test-secret-with-at-least-32-bytes"
    assert settings.cors_origin_list == ["http://localhost:5173", "https://example.test"]


def test_configuration_rejects_non_postgresql_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///attendance.db")
    monkeypatch.setenv("JWT_SECRET", "test-secret-with-at-least-32-bytes")

    with pytest.raises(ValidationError, match="must use PostgreSQL"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_configuration_rejects_short_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:password@db:5432/app")
    monkeypatch.setenv("JWT_SECRET", "too-short")

    with pytest.raises(ValidationError, match="at least 32 bytes"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_configuration_rejects_unmigrated_embedding_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:password@db:5432/app")
    monkeypatch.setenv("JWT_SECRET", "test-secret-with-at-least-32-bytes")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "768")

    with pytest.raises(ValidationError, match="migrated vector dimension of 384"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_configuration_rejects_invalid_answer_confidence_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:password@db:5432/app")
    monkeypatch.setenv("JWT_SECRET", "test-secret-with-at-least-32-bytes")
    monkeypatch.setenv("ANSWER_CONFIDENCE_THRESHOLD", "1.1")

    with pytest.raises(ValidationError, match="must be between 0 and 1"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_configuration_rejects_nonpositive_export_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:password@db:5432/app")
    monkeypatch.setenv("JWT_SECRET", "test-secret-with-at-least-32-bytes")
    monkeypatch.setenv("EXPORT_TTL_SECONDS", "0")

    with pytest.raises(ValidationError, match="Export settings must be positive"):
        Settings(_env_file=None)  # type: ignore[call-arg]
