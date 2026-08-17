from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from attendance.db.models.documents import (
    ChunkEmbedding,
    DocumentChunk,
    DocumentVersion,
    ExtractedUnit,
)
from attendance.domain.security import AuthorizedScope, ClassificationLevel
from attendance.providers.embeddings.base import EmbeddingProvider


@dataclass(frozen=True)
class Candidate:
    chunk_id: UUID
    document_version_id: UUID
    content: str
    source_locator: dict[str, Any]
    method: str
    score: float
    extraction_confidence: float
    review_status: str


def _scope_predicates(
    scope: AuthorizedScope, entity_id: UUID, module: str, classification: ClassificationLevel
) -> list[Any]:
    return [
        DocumentChunk.product_id == scope.product_id,
        DocumentChunk.tenant_id == scope.tenant_id,
        DocumentChunk.entity_id == entity_id,
        DocumentChunk.module == module,
        DocumentChunk.classification <= int(classification),
        DocumentVersion.is_current.is_(True),
    ]


class KeywordRetriever:
    def retrieve(
        self,
        session: Session,
        scope: AuthorizedScope,
        *,
        question: str,
        entity_id: UUID,
        module: str,
        classification: ClassificationLevel,
        limit: int,
    ) -> list[Candidate]:
        query = func.websearch_to_tsquery("english", question)
        rank = func.ts_rank_cd(DocumentChunk.search_vector, query)
        rows = session.execute(
            select(DocumentChunk, ExtractedUnit, rank.label("rank"))
            .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
            .join(ExtractedUnit, ExtractedUnit.id == DocumentChunk.extracted_unit_id)
            .where(*_scope_predicates(scope, entity_id, module, classification))
            .where(DocumentChunk.search_vector.op("@@")(query))
            .order_by(rank.desc(), DocumentChunk.id)
            .limit(limit)
        ).all()
        return [
            Candidate(
                chunk_id=chunk.id,
                document_version_id=chunk.document_version_id,
                content=chunk.content,
                source_locator=chunk.source_locator,
                method="keyword",
                score=float(rank_value),
                extraction_confidence=float(unit.extraction_confidence),
                review_status=unit.review_status,
            )
            for chunk, unit, rank_value in rows
        ]


class VectorRetriever:
    def __init__(self, provider: EmbeddingProvider, score_threshold: float = 0.25) -> None:
        self.provider = provider
        self.score_threshold = score_threshold

    def index_authorized_missing(
        self,
        session: Session,
        scope: AuthorizedScope,
        *,
        entity_id: UUID,
        module: str,
        classification: ClassificationLevel,
    ) -> int:
        chunks = session.scalars(
            select(DocumentChunk)
            .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
            .outerjoin(
                ChunkEmbedding,
                (ChunkEmbedding.chunk_id == DocumentChunk.id)
                & (ChunkEmbedding.model_name == self.provider.model_name)
                & (ChunkEmbedding.model_version == self.provider.model_version),
            )
            .where(*_scope_predicates(scope, entity_id, module, classification))
            .where(ChunkEmbedding.id.is_(None))
        ).all()
        if not chunks:
            return 0
        vectors = self.provider.embed([chunk.content for chunk in chunks])
        for chunk, vector in zip(chunks, vectors, strict=True):
            session.add(
                ChunkEmbedding(
                    chunk_id=chunk.id,
                    product_id=chunk.product_id,
                    tenant_id=chunk.tenant_id,
                    entity_id=chunk.entity_id,
                    module=chunk.module,
                    classification=chunk.classification,
                    model_name=self.provider.model_name,
                    model_version=self.provider.model_version,
                    embedding=vector,
                )
            )
        session.flush()
        return len(chunks)

    def retrieve(
        self,
        session: Session,
        scope: AuthorizedScope,
        *,
        question: str,
        entity_id: UUID,
        module: str,
        classification: ClassificationLevel,
        limit: int,
    ) -> list[Candidate]:
        has_embedding = session.scalar(
            select(ChunkEmbedding.id)
            .join(DocumentChunk, DocumentChunk.id == ChunkEmbedding.chunk_id)
            .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
            .where(*_scope_predicates(scope, entity_id, module, classification))
            .where(
                ChunkEmbedding.model_name == self.provider.model_name,
                ChunkEmbedding.model_version == self.provider.model_version,
            )
            .limit(1)
        )
        if has_embedding is None:
            return []
        query_vector = self.provider.embed([question])[0]
        distance = ChunkEmbedding.embedding.cosine_distance(query_vector)
        rows = session.execute(
            select(DocumentChunk, ExtractedUnit, distance.label("distance"))
            .join(ChunkEmbedding, ChunkEmbedding.chunk_id == DocumentChunk.id)
            .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
            .join(ExtractedUnit, ExtractedUnit.id == DocumentChunk.extracted_unit_id)
            .where(*_scope_predicates(scope, entity_id, module, classification))
            .where(
                ChunkEmbedding.model_name == self.provider.model_name,
                ChunkEmbedding.model_version == self.provider.model_version,
            )
            .order_by(distance, DocumentChunk.id)
            .limit(limit)
        ).all()
        candidates = [
            Candidate(
                chunk_id=chunk.id,
                document_version_id=chunk.document_version_id,
                content=chunk.content,
                source_locator=chunk.source_locator,
                method="vector",
                score=max(0.0, 1.0 - float(distance_value)),
                extraction_confidence=float(unit.extraction_confidence),
                review_status=unit.review_status,
            )
            for chunk, unit, distance_value in rows
        ]
        return [candidate for candidate in candidates if candidate.score >= self.score_threshold]
