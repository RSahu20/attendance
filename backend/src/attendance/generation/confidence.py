from attendance.domain.generation import (
    ConfidenceBand,
    ConfidenceResult,
    GenerationContext,
    ValidatedCitation,
)
from attendance.domain.retrieval import RetrievalMode


class ConfidenceScorer:
    def score(
        self,
        mode: RetrievalMode,
        context: GenerationContext,
        citations: list[ValidatedCitation],
    ) -> ConfidenceResult:
        if mode == RetrievalMode.STRUCTURED:
            score = 0.95 if context.structured_result is not None else 0.0
        else:
            cited_ids = {citation.evidence_id for citation in citations}
            cited = [item for item in context.evidence if item.evidence_id in cited_ids]
            coverage = len(cited_ids) / max(1, len(context.evidence))
            extraction = sum(item.extraction_confidence for item in cited) / max(1, len(cited))
            method_agreement = (
                1.0 if any(len(item.retrieval_methods) > 1 for item in cited) else 0.5
            )
            score = 0.35 + 0.20 * coverage + 0.25 * extraction + 0.10 * method_agreement
            if mode == RetrievalMode.HYBRID and context.structured_result is not None:
                score += 0.10
            if any(item.review_status == "review_required" for item in cited):
                score -= 0.15
            if any(item.injection_detected for item in cited):
                score -= 0.20
        normalized = round(max(0.0, min(1.0, score)), 4)
        band = (
            ConfidenceBand.HIGH
            if normalized >= 0.80
            else ConfidenceBand.MEDIUM
            if normalized >= 0.55
            else ConfidenceBand.LOW
        )
        return ConfidenceResult(score=normalized, band=band)
