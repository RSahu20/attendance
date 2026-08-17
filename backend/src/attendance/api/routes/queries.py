from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from attendance.api.dependencies import get_authorized_scope
from attendance.config import Settings, get_settings
from attendance.db.session import get_db
from attendance.domain.generation import AnswerResponse
from attendance.domain.retrieval import RetrievalMode, RetrievalRequest
from attendance.domain.security import AuthorizedScope
from attendance.generation.service import AnswerService
from attendance.providers.embeddings.base import EmbeddingProvider
from attendance.providers.embeddings.sentence_transformer import SentenceTransformerProvider
from attendance.providers.llm import LLMProvider, MockProvider, OpenAIProvider
from attendance.retrieval.documents import VectorRetriever
from attendance.retrieval.router import QueryRouter
from attendance.retrieval.service import RetrievalService

router = APIRouter(prefix="/api/v1", tags=["retrieval"])


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    return SentenceTransformerProvider(settings.embedding_model)


@lru_cache
def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "mock":
        return MockProvider()
    if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
        raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
    return OpenAIProvider(
        settings.openai_api_key.get_secret_value(),
        settings.openai_model,
    )


@router.post("/queries", response_model=AnswerResponse)
def query(
    request: RetrievalRequest,
    scope: Annotated[AuthorizedScope, Depends(get_authorized_scope)],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
    llm_provider: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> AnswerResponse:
    mode = QueryRouter().route(request.question).mode
    permissions = ["audit:write"]
    if mode in (RetrievalMode.STRUCTURED, RetrievalMode.HYBRID):
        permissions.append("attendance:read")
    if mode in (RetrievalMode.DOCUMENT, RetrievalMode.HYBRID):
        permissions.append("document:read")
    if not all(
        scope.permits(
            permission,
            entity_id=request.entity_id,
            module=request.module,
            classification=request.classification,
        )
        for permission in permissions
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Requested scope is unavailable"
        )
    vector = VectorRetriever(provider, settings.semantic_score_threshold)
    retrieval = RetrievalService(vector, settings.retrieval_limit)
    return AnswerService(
        retrieval,
        llm_provider,
        settings.answer_confidence_threshold,
    ).answer(session, scope, request)
