from uuid import uuid4

from sqlalchemy.orm import Session

from attendance.audit.service import append_audit_event
from attendance.domain.retrieval import (
    EvidenceItem,
    RetrievalMode,
    RetrievalRequest,
    RetrievalResponse,
)
from attendance.domain.security import AuthorizedScope
from attendance.retrieval.documents import Candidate, KeywordRetriever, VectorRetriever
from attendance.retrieval.router import QueryRouter
from attendance.retrieval.structured import StructuredRetriever


class RetrievalService:
    def __init__(self, vector: VectorRetriever, limit: int = 8) -> None:
        self.router = QueryRouter()
        self.structured = StructuredRetriever()
        self.keyword = KeywordRetriever()
        self.vector = vector
        self.limit = limit

    def retrieve(
        self, session: Session, scope: AuthorizedScope, request: RetrievalRequest
    ) -> RetrievalResponse:
        decision = self.router.route(request.question)
        structured = None
        candidates: list[Candidate] = []
        if decision.metric:
            structured = self.structured.retrieve(
                session,
                scope,
                entity_id=request.entity_id,
                module=request.module,
                classification=request.classification,
                metric=decision.metric,
                filters=request.filters,
            )
        if decision.mode in (RetrievalMode.DOCUMENT, RetrievalMode.HYBRID):
            document_query = decision.document_query or request.question
            keyword = self.keyword.retrieve(
                session,
                scope,
                question=document_query,
                entity_id=request.entity_id,
                module=request.module,
                classification=request.classification,
                limit=self.limit,
            )
            vector = self.vector.retrieve(
                session,
                scope,
                question=document_query,
                entity_id=request.entity_id,
                module=request.module,
                classification=request.classification,
                limit=self.limit,
            )
            candidates = self._fuse(keyword, vector)
        request_id = uuid4()
        event = append_audit_event(
            session,
            scope,
            request_id=request_id,
            action="retrieval.completed",
            resource_type="query",
            outcome="available" if structured or candidates else "unavailable",
            entity_id=request.entity_id,
            module=request.module,
            classification=request.classification,
            metadata={"mode": decision.mode.value, "evidence_count": len(candidates)},
        )
        session.flush()
        audit_id = event.id
        session.commit()
        return RetrievalResponse(
            request_id=request_id,
            audit_id=audit_id,
            retrieval_mode=decision.mode,
            available=bool(structured or candidates),
            unavailable_reason=None
            if structured or candidates
            else "No authorized evidence is available",
            structured_result=structured,
            evidence=[
                EvidenceItem(
                    evidence_id=f"ev_{index}",
                    chunk_id=item.chunk_id,
                    document_version_id=item.document_version_id,
                    content=item.content,
                    source_locator=item.source_locator,
                    retrieval_methods=item.method.split("+"),
                    score=item.score,
                    extraction_confidence=item.extraction_confidence,
                    review_status=item.review_status,
                )
                for index, item in enumerate(candidates, 1)
            ],
        )

    def _fuse(self, *lists: list[Candidate]) -> list[Candidate]:
        merged: dict[object, tuple[Candidate, float, set[str]]] = {}
        for values in lists:
            for rank, item in enumerate(values, 1):
                prior = merged.get(item.chunk_id)
                score = 1 / (60 + rank)
                merged[item.chunk_id] = (
                    item,
                    score + (prior[1] if prior else 0),
                    ({item.method} | (prior[2] if prior else set())),
                )
        ordered = sorted(merged.values(), key=lambda value: value[1], reverse=True)[: self.limit]
        return [
            Candidate(**{**item.__dict__, "method": "+".join(sorted(methods)), "score": score})
            for item, score, methods in ordered
        ]
