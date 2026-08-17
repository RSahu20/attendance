from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from attendance.domain.attendance import ExtractionMethod, ReviewStatus


class IngestionError(Exception):
    """Safe, categorized ingestion failure suitable for an API response."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class ParsedUnit:
    source_unit_key: str
    unit_type: str
    source_locator: dict[str, Any]
    raw_text: str
    structured_data: dict[str, Any] = field(default_factory=dict)
    extraction_method: ExtractionMethod = ExtractionMethod.NATIVE
    extraction_confidence: Decimal = Decimal("1")
    review_status: ReviewStatus = ReviewStatus.ACCEPTED


@dataclass(frozen=True)
class RecordIssue:
    source_unit_key: str
    code: str
    message: str
    warnings: tuple[str, ...] = ()
