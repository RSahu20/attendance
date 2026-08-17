from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from attendance.audit.service import append_audit_event
from attendance.db.rls import set_authorization_context
from attendance.domain.generation import (
    AnswerResponse,
    AnswerStatus,
    ConfidenceBand,
    ConfidenceResult,
    LLMRequest,
    ValidatedCitation,
)
from attendance.domain.retrieval import RetrievalMode, RetrievalRequest
from attendance.domain.security import AuthorizedScope
from attendance.generation.citation_validator import CitationValidator
from attendance.generation.confidence import ConfidenceScorer
from attendance.generation.context import ContextBuilder
from attendance.providers.llm.base import LLMProvider
from attendance.retrieval.service import RetrievalService


class AnswerService:
    def __init__(
        self,
        retrieval: RetrievalService,
        provider: LLMProvider,
        confidence_threshold: float,
    ) -> None:
        self.retrieval = retrieval
        self.provider = provider
        self.confidence_threshold = confidence_threshold
        self.context_builder = ContextBuilder()
        self.citation_validator = CitationValidator()
        self.confidence_scorer = ConfidenceScorer()

    def answer(
        self, session: Session, scope: AuthorizedScope, request: RetrievalRequest
    ) -> AnswerResponse:
        retrieval = self.retrieval.retrieve(session, scope, request)
        set_authorization_context(session, scope)
        if not retrieval.available:
            return self._unavailable(
                session,
                scope,
                request,
                retrieval.request_id,
                retrieval.retrieval_mode,
                "INSUFFICIENT_AUTHORIZED_EVIDENCE",
            )

        context = self.context_builder.build(session, scope, request, retrieval)
        if retrieval.retrieval_mode == RetrievalMode.STRUCTURED:
            answer = self._structured_answer(context.structured_result)
            confidence = self.confidence_scorer.score(
                retrieval.retrieval_mode, context, citations=[]
            )
            return self._answered(
                session,
                scope,
                request,
                retrieval.request_id,
                retrieval.retrieval_mode,
                answer,
                [],
                confidence,
                injection_count=0,
            )

        if not context.evidence:
            return self._unavailable(
                session,
                scope,
                request,
                retrieval.request_id,
                retrieval.retrieval_mode,
                "INSUFFICIENT_AUTHORIZED_EVIDENCE",
            )
        llm_request = LLMRequest(question=request.question, context=context)
        try:
            output = self.provider.generate(llm_request)
            validation = self.citation_validator.validate(output, context, citations_required=True)
            if validation.errors:
                output = self.provider.generate(
                    llm_request.model_copy(update={"correction_errors": validation.errors})
                )
                validation = self.citation_validator.validate(
                    output, context, citations_required=True
                )
        except Exception:
            return self._unavailable(
                session,
                scope,
                request,
                retrieval.request_id,
                retrieval.retrieval_mode,
                "PROVIDER_UNAVAILABLE",
            )
        if validation.errors:
            return self._unavailable(
                session,
                scope,
                request,
                retrieval.request_id,
                retrieval.retrieval_mode,
                "INVALID_CITATIONS",
            )
        confidence = self.confidence_scorer.score(
            retrieval.retrieval_mode, context, validation.citations
        )
        if confidence.score < self.confidence_threshold:
            return self._unavailable(
                session,
                scope,
                request,
                retrieval.request_id,
                retrieval.retrieval_mode,
                "LOW_CONFIDENCE",
                confidence=confidence,
            )
        return self._answered(
            session,
            scope,
            request,
            retrieval.request_id,
            retrieval.retrieval_mode,
            output.answer,
            validation.citations,
            confidence,
            injection_count=sum(item.injection_detected for item in context.evidence),
        )

    def _structured_answer(self, result: dict[str, Any] | None) -> str:
        if not result:
            return "No authorized structured result is available."
        metric = str(result["metric"]).replace("_", " ")
        return f"The authorized {metric} is {result['value']}."

    def _answered(
        self,
        session: Session,
        scope: AuthorizedScope,
        request: RetrievalRequest,
        request_id: UUID,
        mode: RetrievalMode,
        answer: str,
        citations: list[ValidatedCitation],
        confidence: ConfidenceResult,
        *,
        injection_count: int,
    ) -> AnswerResponse:
        event = append_audit_event(
            session,
            scope,
            request_id=request_id,
            action="generation.completed",
            resource_type="query",
            outcome="answered",
            entity_id=request.entity_id,
            module=request.module,
            classification=request.classification,
            metadata={
                "provider": self.provider.name,
                "model": self.provider.model,
                "mode": mode.value,
                "citation_count": len(citations),
                "confidence": confidence.score,
                "injection_evidence_count": injection_count,
            },
        )
        session.flush()
        audit_id = event.id
        session.commit()
        return self._response(
            scope,
            request,
            request_id,
            audit_id,
            mode,
            answer,
            citations,
            confidence,
            AnswerStatus.ANSWERED,
        )

    def _unavailable(
        self,
        session: Session,
        scope: AuthorizedScope,
        request: RetrievalRequest,
        request_id: UUID,
        mode: RetrievalMode,
        reason: str,
        confidence: ConfidenceResult | None = None,
    ) -> AnswerResponse:
        set_authorization_context(session, scope)
        event = append_audit_event(
            session,
            scope,
            request_id=request_id,
            action="generation.completed",
            resource_type="query",
            outcome="unavailable",
            entity_id=request.entity_id,
            module=request.module,
            classification=request.classification,
            metadata={
                "provider": self.provider.name,
                "model": self.provider.model,
                "reason": reason,
            },
        )
        session.flush()
        audit_id = event.id
        session.commit()
        return self._response(
            scope,
            request,
            request_id,
            audit_id,
            mode,
            (
                "The answer is unavailable because sufficient authorized evidence "
                "could not be validated."
            ),
            [],
            confidence or ConfidenceResult(score=0, band=ConfidenceBand.LOW),
            AnswerStatus.UNAVAILABLE,
            reason,
        )

    def _response(
        self,
        scope: AuthorizedScope,
        request: RetrievalRequest,
        request_id: UUID,
        audit_id: UUID,
        mode: RetrievalMode,
        answer: str,
        citations: list[ValidatedCitation],
        confidence: ConfidenceResult,
        status: AnswerStatus,
        unavailable_reason: str | None = None,
    ) -> AnswerResponse:
        return AnswerResponse(
            answer=answer,
            tenant_context={"tenant_id": scope.tenant_id},
            entity_context={"entity_ids": [request.entity_id]},
            role_context={"roles": sorted(scope.role_ids, key=str)},
            citations=citations,
            confidence=confidence,
            retrieval_mode=mode,
            request_id=request_id,
            audit_id=audit_id,
            status=status,
            unavailable_reason=unavailable_reason,
        )
