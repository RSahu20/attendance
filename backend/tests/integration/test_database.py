import pytest
from sqlalchemy import create_engine, text


@pytest.mark.integration
def test_postgresql_connectivity(database_url: str) -> None:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
            assert connection.dialect.name == "postgresql"
    finally:
        engine.dispose()


@pytest.mark.integration
def test_pgvector_extension_is_available(database_url: str) -> None:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            version = connection.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).scalar_one_or_none()
    finally:
        engine.dispose()

    assert version is not None
