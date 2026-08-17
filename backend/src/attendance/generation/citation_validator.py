import re
from dataclasses import dataclass

from attendance.domain.generation import (
    GenerationContext,
    ProviderOutput,
    ValidatedCitation,
)


@dataclass(frozen=True)
class CitationValidation:
    citations: list[ValidatedCitation]
    errors: list[str]


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 2}


class CitationValidator:
    def validate(
        self, output: ProviderOutput, context: GenerationContext, *, citations_required: bool
    ) -> CitationValidation:
        allowed = {item.evidence_id: item for item in context.evidence}
        validated = []
        errors = []
        seen: set[str] = set()
        for citation in output.citations:
            item = allowed.get(citation.evidence_id)
            if item is None:
                errors.append(f"Unknown evidence ID: {citation.evidence_id}")
                continue
            if citation.evidence_id in seen:
                continue
            if not item.source_locator:
                errors.append(f"Evidence has no source locator: {citation.evidence_id}")
                continue
            claim_tokens = _tokens(citation.claim)
            evidence_tokens = _tokens(item.content)
            overlap = len(claim_tokens & evidence_tokens) / max(1, len(claim_tokens))
            if overlap < 0.35:
                errors.append(f"Claim is not supported by evidence: {citation.evidence_id}")
                continue
            seen.add(citation.evidence_id)
            validated.append(
                ValidatedCitation(
                    evidence_id=item.evidence_id,
                    chunk_id=item.chunk_id,
                    document_version_id=item.document_version_id,
                    source_locator=item.source_locator,
                    claim=citation.claim,
                )
            )
        if citations_required and not validated:
            errors.append("At least one valid authorized citation is required")
        if citations_required and validated:
            answer_tokens = _tokens(output.answer)
            supporting_tokens: set[str] = set()
            for citation in validated:
                supporting_tokens.update(_tokens(citation.claim))
                supporting_tokens.update(_tokens(allowed[citation.evidence_id].content))
            answer_overlap = len(answer_tokens & supporting_tokens) / max(1, len(answer_tokens))
            if answer_overlap < 0.20:
                errors.append("The answer is not grounded in its cited evidence")
        return CitationValidation(citations=validated, errors=errors)
