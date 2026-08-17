from attendance.domain.retrieval import RetrievalMode, StructuredMetric
from attendance.retrieval.router import QueryRouter


def test_router_selects_structured_document_and_hybrid_modes() -> None:
    router = QueryRouter()

    structured = router.route("How many attendance records are present?")
    document = router.route("Engineering")
    hybrid = router.route("Count attendance records with supporting evidence Engineering")

    assert structured.mode == RetrievalMode.STRUCTURED
    assert structured.metric == StructuredMetric.COUNT
    assert document.mode == RetrievalMode.DOCUMENT
    assert hybrid.mode == RetrievalMode.HYBRID
    assert hybrid.document_query == "Engineering"


def test_router_controls_unsupported_question() -> None:
    assert QueryRouter().route("??").mode == RetrievalMode.UNSUPPORTED
