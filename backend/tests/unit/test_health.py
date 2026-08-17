from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from attendance.db.session import get_db
from attendance.main import app


class ScalarResult:
    def __init__(self, value: object) -> None:
        self.value = value

    def scalar_one(self) -> object:
        return self.value

    def scalar_one_or_none(self) -> object | None:
        return self.value


class HealthySession:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, _: object) -> ScalarResult:
        self.calls += 1
        return ScalarResult(1 if self.calls == 1 else "0.8.0")


class UnavailableSession:
    def execute(self, _: object) -> ScalarResult:
        raise OperationalError("SELECT 1", {}, RuntimeError("database unavailable"))


class MissingVectorSession:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, _: object) -> ScalarResult:
        self.calls += 1
        return ScalarResult(1 if self.calls == 1 else None)


def test_liveness() -> None:
    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_when_dependencies_are_available() -> None:
    app.dependency_overrides[get_db] = HealthySession
    try:
        with TestClient(app) as client:
            response = client.get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"postgresql": "available", "pgvector": "available"},
        "pgvector_version": "0.8.0",
    }


def test_readiness_when_postgresql_is_unavailable() -> None:
    app.dependency_overrides[get_db] = UnavailableSession
    try:
        with TestClient(app) as client:
            response = client.get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["checks"] == {
        "postgresql": "unavailable",
        "pgvector": "unavailable",
    }


def test_readiness_when_pgvector_is_missing() -> None:
    app.dependency_overrides[get_db] = MissingVectorSession
    try:
        with TestClient(app) as client:
            response = client.get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["checks"] == {
        "postgresql": "available",
        "pgvector": "unavailable",
    }
