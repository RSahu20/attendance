from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from math import sqrt
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from attendance.api.routes.queries import get_embedding_provider, get_llm_provider
from attendance.config import get_settings
from attendance.domain.generation import ProviderCitation, ProviderOutput
from attendance.domain.security import ClassificationLevel
from attendance.main import app
from attendance.providers.embeddings.base import EmbeddingProvider
from attendance.providers.llm.mock import MockProvider
from attendance.retrieval.documents import VectorRetriever
from attendance.retrieval.indexing import EmbeddingIndexer
from attendance.security.authentication import Principal
from attendance.security.authorization import AuthorizationService
from tests.integration.conftest import SecuritySeed


class DeterministicEmbeddingProvider(EmbeddingProvider):
    model_name = "test-hash-embedding"
    model_version = "1"
    dimension = 384

    def embed(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text_value in texts:
            vector = [0.0] * self.dimension
            for token in text_value.lower().replace("|", " ").split():
                vector[sum(token.encode()) % self.dimension] += 1.0
            norm = sqrt(sum(value * value for value in vector)) or 1.0
            results.append([value / norm for value in vector])
        return results


class InventedCitationProvider(MockProvider):
    name = "invalid-test-provider"
    model = "invalid-v1"

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, request: Any) -> ProviderOutput:
        self.calls += 1
        return ProviderOutput(
            answer="Tenant B has secret data.",
            citations=[ProviderCitation(evidence_id="ev_invented", claim="secret data")],
        )


def _token(subject: str) -> str:
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


def _headers(seed: SecuritySeed, tenant_id: Any | None = None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token(seed.subject)}",
        "X-Product-ID": str(seed.product_id),
        "X-Tenant-ID": str(tenant_id or seed.tenant_a_id),
    }


@pytest.fixture
def retrieval_seed(
    security_seed: SecuritySeed, database_url: str, migration_database_url: str
) -> Iterator[SecuritySeed]:
    app.dependency_overrides[get_embedding_provider] = lambda: DeterministicEmbeddingProvider()
    app.dependency_overrides[get_llm_provider] = lambda: MockProvider()
    csv_data = (
        b"Date,Employee ID,Employee Name,Status,Department\n"
        b"2026-08-01,RET-001,Robin Fiction,Present,Engineering\n"
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/documents",
            headers=_headers(security_seed),
            files={"file": ("retrieval.csv", csv_data, "text/csv")},
            data={
                "entity_id": str(security_seed.entity_high_id),
                "module": "attendance",
                "classification": "2",
                "logical_name": "retrieval-test",
            },
        )
        assert response.status_code == 201, response.text
    engine = create_engine(database_url)
    with Session(engine) as session:
        scope = AuthorizationService().resolve_scope(
            session,
            Principal(subject=security_seed.subject),
            product_id=security_seed.product_id,
            tenant_id=security_seed.tenant_a_id,
        )
        count = EmbeddingIndexer(VectorRetriever(DeterministicEmbeddingProvider())).index(
            session,
            scope,
            entity_id=security_seed.entity_high_id,
            module="attendance",
            classification=ClassificationLevel.CONFIDENTIAL,
        )
        assert count == 1
    engine.dispose()
    yield security_seed
    app.dependency_overrides.pop(get_embedding_provider, None)
    app.dependency_overrides.pop(get_llm_provider, None)
    admin = create_engine(migration_database_url)
    with admin.begin() as connection:
        connection.execute(
            text("DELETE FROM documents WHERE product_id = :id"), {"id": security_seed.product_id}
        )
        connection.execute(text("TRUNCATE audit_events"))
    admin.dispose()


@pytest.mark.integration
def test_structured_keyword_vector_and_hybrid_retrieval(retrieval_seed: SecuritySeed) -> None:
    base = {
        "entity_id": str(retrieval_seed.entity_high_id),
        "module": "attendance",
        "classification": 2,
    }
    with TestClient(app) as client:
        structured = client.post(
            "/api/v1/queries",
            headers=_headers(retrieval_seed),
            json={**base, "question": "How many attendance records?"},
        )
        document = client.post(
            "/api/v1/queries",
            headers=_headers(retrieval_seed),
            json={**base, "question": "Engineering"},
        )
        hybrid = client.post(
            "/api/v1/queries",
            headers=_headers(retrieval_seed),
            json={**base, "question": "Count Engineering evidence"},
        )
    assert structured.status_code == 200
    assert document.status_code == 200
    assert hybrid.status_code == 200
    assert structured.json()["status"] == "answered"
    assert structured.json()["answer"] == "The authorized count is 1.0."
    assert structured.json()["confidence"] == {"score": 0.95, "band": "high"}
    assert document.json()["status"] == "answered"
    assert document.json()["citations"][0]["validated"] is True
    assert document.json()["citations"][0]["claim"].find("RET-001") >= 0
    assert hybrid.json()["retrieval_mode"] == "hybrid"
    assert hybrid.json()["status"] == "answered", hybrid.json()
    assert hybrid.json()["citations"]


@pytest.mark.integration
def test_retrieval_enforces_scope_and_controlled_unavailable(retrieval_seed: SecuritySeed) -> None:
    with TestClient(app) as client:
        unavailable = client.post(
            "/api/v1/queries",
            headers=_headers(retrieval_seed),
            json={
                "question": "??",
                "entity_id": str(retrieval_seed.entity_high_id),
                "classification": 2,
            },
        )
        entity_denied = client.post(
            "/api/v1/queries",
            headers=_headers(retrieval_seed),
            json={
                "question": "How many records?",
                "entity_id": str(retrieval_seed.entity_low_id),
                "classification": 2,
            },
        )
        tenant_denied = client.post(
            "/api/v1/queries",
            headers=_headers(retrieval_seed, retrieval_seed.tenant_b_id),
            json={
                "question": "How many records?",
                "entity_id": str(retrieval_seed.entity_high_id),
                "classification": 2,
            },
        )
        classification_denied = client.post(
            "/api/v1/queries",
            headers=_headers(retrieval_seed),
            json={
                "question": "How many records?",
                "entity_id": str(retrieval_seed.entity_high_id),
                "classification": 3,
            },
        )
    assert unavailable.status_code == 200
    assert unavailable.json()["status"] == "unavailable"
    assert unavailable.json()["unavailable_reason"] == "INSUFFICIENT_AUTHORIZED_EVIDENCE"
    assert entity_denied.status_code == 403
    assert tenant_denied.status_code == 403
    assert classification_denied.status_code == 403


@pytest.mark.integration
def test_invalid_citations_retry_once_then_return_unavailable(
    retrieval_seed: SecuritySeed,
) -> None:
    invalid_provider = InventedCitationProvider()
    app.dependency_overrides[get_llm_provider] = lambda: invalid_provider
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/queries",
            headers=_headers(retrieval_seed),
            json={
                "question": "Engineering",
                "entity_id": str(retrieval_seed.entity_high_id),
                "module": "attendance",
                "classification": 2,
            },
        )
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["unavailable_reason"] == "INVALID_CITATIONS"
    assert response.json()["citations"] == []
    assert invalid_provider.calls == 2
