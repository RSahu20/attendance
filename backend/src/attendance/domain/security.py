from enum import IntEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ClassificationLevel(IntEnum):
    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    RESTRICTED = 3


class ScopeGrant(BaseModel):
    """One indivisible authorization grant.

    Grants remain separate so permissions and classification ceilings from
    different roles cannot be combined into broader access.
    """

    model_config = ConfigDict(frozen=True)

    role_id: UUID
    entity_id: UUID | None
    module: str | None
    classification_ceiling: ClassificationLevel
    permissions: frozenset[str]

    def permits(
        self,
        permission: str,
        *,
        entity_id: UUID | None = None,
        module: str | None = None,
        classification: ClassificationLevel = ClassificationLevel.PUBLIC,
    ) -> bool:
        return (
            permission in self.permissions
            and (self.entity_id is None or self.entity_id == entity_id)
            and (self.module is None or self.module == module)
            and self.classification_ceiling >= classification
        )


class AuthorizedScope(BaseModel):
    """Server-resolved access scope for one product and tenant request."""

    model_config = ConfigDict(frozen=True)

    user_id: UUID
    subject: str
    product_id: UUID
    tenant_id: UUID
    grants: tuple[ScopeGrant, ...]

    @property
    def role_ids(self) -> frozenset[UUID]:
        return frozenset(grant.role_id for grant in self.grants)

    def permits(
        self,
        permission: str,
        *,
        entity_id: UUID | None = None,
        module: str | None = None,
        classification: ClassificationLevel = ClassificationLevel.PUBLIC,
    ) -> bool:
        return any(
            grant.permits(
                permission,
                entity_id=entity_id,
                module=module,
                classification=classification,
            )
            for grant in self.grants
        )

    def has_permission_anywhere(self, permission: str) -> bool:
        return any(permission in grant.permissions for grant in self.grants)
