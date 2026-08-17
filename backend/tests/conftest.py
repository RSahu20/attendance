import os

import pytest
from sqlalchemy.engine import make_url

# Unit tests must be importable without a developer's local .env file. These are
# non-secret test-only values; integration tests inherit Compose's DATABASE_URL.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://attendance@localhost/attendance")
os.environ.setdefault("JWT_SECRET", "unit-test-secret-not-for-runtime-00000000")
os.environ.setdefault("APP_ENV", "test")


@pytest.fixture
def database_url() -> str:
    return os.environ["DATABASE_URL"]


@pytest.fixture
def migration_database_url(database_url: str) -> str:
    return os.environ.get("MIGRATION_DATABASE_URL", database_url)


@pytest.fixture
def runtime_database_user(database_url: str) -> str:
    username = make_url(database_url).username
    assert username is not None
    return username
