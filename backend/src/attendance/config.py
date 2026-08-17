from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded exclusively from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str
    migration_database_url: str | None = None
    app_env: Literal["development", "test", "staging", "production"] = "development"
    jwt_secret: SecretStr
    jwt_issuer: str = "attendance-intelligence"
    jwt_audience: str = "attendance-api"
    cors_origins: str = "http://localhost:5173"
    llm_provider: Literal["mock", "openai"] = "mock"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4.1-mini"
    answer_confidence_threshold: float = 0.55
    embedding_provider: str = "local_sentence_transformer"
    embedding_dimension: int = 384
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    retrieval_limit: int = 8
    semantic_score_threshold: float = 0.25
    ocr_provider: str = "tesseract"
    storage_provider: str = "local"
    storage_root: str = "/data/attendance"
    export_ttl_seconds: int = 3600
    export_max_records: int = 10000
    max_upload_bytes: int = 25 * 1024 * 1024
    ocr_confidence_threshold: float = 0.80

    @field_validator("database_url")
    @classmethod
    def validate_postgresql_url(cls, value: str) -> str:
        if not value.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("DATABASE_URL must use PostgreSQL with the psycopg driver")
        return value

    @field_validator("migration_database_url")
    @classmethod
    def validate_migration_postgresql_url(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("MIGRATION_DATABASE_URL must use PostgreSQL")
        return value

    @property
    def alembic_database_url(self) -> str:
        return self.migration_database_url or self.database_url

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 bytes")
        return value

    @field_validator("embedding_dimension")
    @classmethod
    def validate_embedding_dimension(cls, value: int) -> int:
        if value != 384:
            raise ValueError("EMBEDDING_DIMENSION must match the migrated vector dimension of 384")
        return value

    @field_validator("max_upload_bytes")
    @classmethod
    def validate_max_upload_bytes(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("MAX_UPLOAD_BYTES must be positive")
        return value

    @field_validator("export_ttl_seconds", "export_max_records")
    @classmethod
    def validate_positive_export_setting(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Export settings must be positive")
        return value

    @field_validator("ocr_confidence_threshold")
    @classmethod
    def validate_ocr_confidence_threshold(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("OCR_CONFIDENCE_THRESHOLD must be between 0 and 1")
        return value

    @field_validator("answer_confidence_threshold")
    @classmethod
    def validate_answer_confidence_threshold(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("ANSWER_CONFIDENCE_THRESHOLD must be between 0 and 1")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
