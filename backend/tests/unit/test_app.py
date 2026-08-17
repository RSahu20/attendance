from fastapi.testclient import TestClient

from attendance.main import app


def test_application_starts_and_serves_openapi() -> None:
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Attendance Intelligence API"


def test_authorization_context_requires_bearer_token() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/auth/context",
            headers={
                "X-Product-ID": "00000000-0000-0000-0000-000000000001",
                "X-Tenant-ID": "00000000-0000-0000-0000-000000000002",
            },
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
