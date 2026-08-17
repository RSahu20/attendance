import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from attendance.domain.security import AuthorizedScope


def set_authorization_context(session: Session, scope: AuthorizedScope) -> None:
    """Set trusted, transaction-local values consumed by PostgreSQL RLS policies."""

    serialized_grants = json.dumps(
        [
            {
                "role_id": str(grant.role_id),
                "entity_id": str(grant.entity_id) if grant.entity_id else None,
                "module": grant.module,
                "classification_ceiling": int(grant.classification_ceiling),
                "permissions": sorted(grant.permissions),
            }
            for grant in scope.grants
        ]
    )
    session.execute(
        text(
            """
            SELECT
                set_config('app.user_id', :user_id, true),
                set_config('app.product_id', :product_id, true),
                set_config('app.tenant_id', :tenant_id, true),
                set_config('app.authorization_grants', :authorization_grants, true)
            """
        ),
        {
            "user_id": str(scope.user_id),
            "product_id": str(scope.product_id),
            "tenant_id": str(scope.tenant_id),
            "authorization_grants": serialized_grants,
        },
    )
