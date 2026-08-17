import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from attendance.db.models.documents import DocumentChunk, DocumentVersion, ExtractedUnit
from attendance.domain.generation import GenerationContext, GenerationContextItem
from attendance.domain.retrieval import RetrievalRequest, RetrievalResponse
from attendance.domain.security import AuthorizedScope

INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?previous", re.IGNORECASE),
    re.compile(r"reveal\s+(the\s+)?system\s+prompt", re.IGNORECASE),
    re.compile(r"change\s+(the\s+)?(tenant|scope|role)", re.IGNORECASE),
    re.compile(r"disregard\s+(your|the)\s+instructions", re.IGNORECASE),
)
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<![\d-])(?:\+?\d[ ()-]?){9,14}\d(?![\d-])")


def sanitize_evidence(content: str) -> tuple[str, bool]:
    injection_detected = any(pattern.search(content) for pattern in INJECTION_PATTERNS)
    sanitized = EMAIL_PATTERN.sub("[EMAIL_REDACTED]", content)
    sanitized = PHONE_PATTERN.sub("[PHONE_REDACTED]", sanitized)
    if injection_detected:
        for pattern in INJECTION_PATTERNS:
            sanitized = pattern.sub("[REDACTED_UNTRUSTED_INSTRUCTION]", sanitized)
        sanitized = "[UNTRUSTED_INSTRUCTION_DETECTED] " + sanitized
    return sanitized, injection_detected


class ContextBuilder:
    def build(
        self,
        session: Session,
        scope: AuthorizedScope,
        request: RetrievalRequest,
        retrieval: RetrievalResponse,
    ) -> GenerationContext:
        if not scope.permits(
            "audit:write",
            entity_id=request.entity_id,
            module=request.module,
            classification=request.classification,
        ):
            return GenerationContext()
        requested: set[UUID] = {item.chunk_id for item in retrieval.evidence}
        if not requested:
            return GenerationContext(structured_result=retrieval.structured_result)
        rows = session.execute(
            select(DocumentChunk, DocumentVersion, ExtractedUnit)
            .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
            .join(ExtractedUnit, ExtractedUnit.id == DocumentChunk.extracted_unit_id)
            .where(
                DocumentChunk.id.in_(requested),
                DocumentChunk.product_id == scope.product_id,
                DocumentChunk.tenant_id == scope.tenant_id,
                DocumentChunk.entity_id == request.entity_id,
                DocumentChunk.module == request.module,
                DocumentChunk.classification <= int(request.classification),
                DocumentVersion.is_current.is_(True),
            )
        ).all()
        verified = {chunk.id: (chunk, version, unit) for chunk, version, unit in rows}
        context_items = []
        for evidence in retrieval.evidence:
            row = verified.get(evidence.chunk_id)
            if row is None:
                continue
            chunk, version, unit = row
            content, injection_detected = sanitize_evidence(chunk.content)
            context_items.append(
                GenerationContextItem(
                    evidence_id=evidence.evidence_id,
                    chunk_id=chunk.id,
                    document_version_id=version.id,
                    content=content,
                    source_locator=chunk.source_locator,
                    retrieval_methods=evidence.retrieval_methods,
                    retrieval_score=evidence.score,
                    extraction_confidence=float(unit.extraction_confidence),
                    review_status=unit.review_status,
                    injection_detected=injection_detected,
                )
            )
        return GenerationContext(
            structured_result=retrieval.structured_result,
            evidence=context_items,
        )
