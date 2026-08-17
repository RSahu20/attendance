from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from attendance.db.models.audit import AuditEvent
from attendance.domain.security import AuthorizedScope, ClassificationLevel


def append_audit_event(
    session: Session,
    scope: AuthorizedScope,
    *,
    action: str,
    resource_type: str,
    outcome: str,
    request_id: UUID | None = None,
    entity_id: UUID | None = None,
    module: str | None = None,
    classification: ClassificationLevel = ClassificationLevel.PUBLIC,
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append an audit event; transaction ownership remains with the caller."""

    event = AuditEvent(
        request_id=request_id or uuid4(),
        actor_user_id=scope.user_id,
        product_id=scope.product_id,
        tenant_id=scope.tenant_id,
        entity_id=entity_id,
        module=module,
        classification=int(classification),
        role_ids=sorted(str(role_id) for role_id in scope.role_ids),
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        event_metadata=metadata or {},
    )
    session.add(event)
    return event
