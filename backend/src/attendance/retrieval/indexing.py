from uuid import UUID

from sqlalchemy.orm import Session

from attendance.db.rls import set_authorization_context
from attendance.domain.security import AuthorizedScope, ClassificationLevel
from attendance.retrieval.documents import VectorRetriever


class EmbeddingIndexer:
    """Explicit writer-authorized embedding backfill outside the query path."""

    def __init__(self, retriever: VectorRetriever) -> None:
        self.retriever = retriever

    def index(
        self,
        session: Session,
        scope: AuthorizedScope,
        *,
        entity_id: UUID,
        module: str,
        classification: ClassificationLevel,
    ) -> int:
        if not scope.permits(
            "document:write",
            entity_id=entity_id,
            module=module,
            classification=classification,
        ):
            raise PermissionError("Requested scope is unavailable")
        set_authorization_context(session, scope)
        count = self.retriever.index_authorized_missing(
            session,
            scope,
            entity_id=entity_id,
            module=module,
            classification=classification,
        )
        session.commit()
        return count
