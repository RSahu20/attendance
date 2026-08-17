import re
from dataclasses import dataclass

from attendance.domain.retrieval import RetrievalMode, StructuredMetric


@dataclass(frozen=True)
class RouteDecision:
    mode: RetrievalMode
    metric: StructuredMetric | None = None
    document_query: str | None = None


class QueryRouter:
    def route(self, question: str) -> RouteDecision:
        lowered = question.lower()
        metric: StructuredMetric | None = None
        if any(term in lowered for term in ("how many", "count", "total records")):
            metric = StructuredMetric.COUNT
        elif "average" in lowered and any(term in lowered for term in ("percentage", "attendance")):
            metric = StructuredMetric.AVERAGE_PERCENTAGE
        elif any(term in lowered for term in ("total hours", "hours worked")):
            metric = StructuredMetric.TOTAL_HOURS
        elif any(term in lowered for term in ("highest percentage", "maximum percentage")):
            metric = StructuredMetric.HIGHEST_PERCENTAGE
        elif any(term in lowered for term in ("lowest percentage", "minimum percentage")):
            metric = StructuredMetric.LOWEST_PERCENTAGE
        elif any(term in lowered for term in ("breakdown", "by status")):
            metric = StructuredMetric.STATUS_BREAKDOWN

        asks_evidence = any(
            term in lowered
            for term in ("evidence", "source", "document", "supporting", "show rows")
        )
        if metric and asks_evidence:
            document_query = question
            for term in (
                "how many",
                "total records",
                "attendance records",
                "supporting evidence",
                "show rows",
                "count",
                "evidence",
                "source",
                "document",
                "with",
            ):
                document_query = re.sub(
                    rf"\b{re.escape(term)}\b", " ", document_query, flags=re.IGNORECASE
                )
            document_query = " ".join(document_query.split())
            return RouteDecision(RetrievalMode.HYBRID, metric, document_query or question)
        if metric:
            return RouteDecision(RetrievalMode.STRUCTURED, metric)
        if any(character.isalnum() for character in lowered):
            return RouteDecision(RetrievalMode.DOCUMENT, document_query=question)
        return RouteDecision(RetrievalMode.UNSUPPORTED)
