import json
import time
from uuid import UUID

import httpx
from attendance.config import get_settings
from attendance.domain.security import ClassificationLevel
from attendance.providers.embeddings.sentence_transformer import (
    SentenceTransformerProvider,
)
from attendance.retrieval.documents import VectorRetriever
from attendance.retrieval.indexing import EmbeddingIndexer
from attendance.security.authentication import Principal
from attendance.security.authorization import AuthorizationService
from demo_ingestion import access_token, seed_scope
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def wait_for_api(client: httpx.Client, attempts: int = 30) -> None:
    for _ in range(attempts):
        try:
            if client.get("/health/ready").status_code == 200:
                return
        except httpx.ConnectError:
            pass
        time.sleep(1)
    raise RuntimeError("API did not become ready")


def main() -> None:
    subject, product_id, tenant_id, entity_id = seed_scope()
    settings = get_settings()
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        scope = AuthorizationService().resolve_scope(
            session,
            Principal(subject=subject),
            product_id=UUID(product_id),
            tenant_id=UUID(tenant_id),
        )
        provider = SentenceTransformerProvider(settings.embedding_model)
        indexed = EmbeddingIndexer(VectorRetriever(provider)).index(
            session,
            scope,
            entity_id=UUID(entity_id),
            module="attendance",
            classification=ClassificationLevel.INTERNAL,
        )
    engine.dispose()

    headers = {
        "Authorization": f"Bearer {access_token(subject)}",
        "X-Product-ID": product_id,
        "X-Tenant-ID": tenant_id,
    }
    common = {
        "entity_id": entity_id,
        "module": "attendance",
        "classification": int(ClassificationLevel.INTERNAL),
    }
    questions = {
        "structured": "How many attendance records?",
        "document": "Engineering",
        "hybrid": "Count attendance records with supporting evidence Engineering",
        "unavailable": "??",
    }
    responses = {}
    with httpx.Client(base_url="http://api:8000", timeout=60) as client:
        wait_for_api(client)
        for name, question in questions.items():
            response = client.post(
                "/api/v1/queries",
                headers=headers,
                json={**common, "question": question},
            )
            response.raise_for_status()
            responses[name] = response.json()
    print(json.dumps({"new_embeddings": indexed, "responses": responses}, indent=2))


if __name__ == "__main__":
    main()
