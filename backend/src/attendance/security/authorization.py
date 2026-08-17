from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from attendance.db.models.identity import Product, Tenant, User
from attendance.db.models.rbac import (
    Permission,
    Role,
    RolePermission,
    UserRoleAssignment,
)
from attendance.domain.security import AuthorizedScope, ClassificationLevel, ScopeGrant
from attendance.security.authentication import Principal


class AuthorizationDenied(Exception):
    """Raised for all unavailable or unauthorized scopes without disclosing existence."""


class AuthorizationService:
    def resolve_scope(
        self,
        session: Session,
        principal: Principal,
        *,
        product_id: UUID,
        tenant_id: UUID,
    ) -> AuthorizedScope:
        user = session.scalar(
            select(User).where(User.subject == principal.subject, User.is_active.is_(True))
        )
        if user is None:
            raise AuthorizationDenied("Requested scope is unavailable")

        active_scope_exists = session.scalar(
            select(Tenant.id)
            .join(Product, Product.id == Tenant.product_id)
            .where(
                Product.id == product_id,
                Product.is_active.is_(True),
                Tenant.id == tenant_id,
                Tenant.is_active.is_(True),
            )
        )
        if active_scope_exists is None:
            raise AuthorizationDenied("Requested scope is unavailable")

        now = datetime.now(UTC)
        assignments = session.scalars(
            select(UserRoleAssignment)
            .join(Role, Role.id == UserRoleAssignment.role_id)
            .where(
                UserRoleAssignment.user_id == user.id,
                UserRoleAssignment.product_id == product_id,
                UserRoleAssignment.tenant_id == tenant_id,
                UserRoleAssignment.is_active.is_(True),
                Role.is_active.is_(True),
                or_(
                    UserRoleAssignment.valid_from.is_(None),
                    UserRoleAssignment.valid_from <= now,
                ),
                or_(
                    UserRoleAssignment.valid_until.is_(None),
                    UserRoleAssignment.valid_until > now,
                ),
            )
        ).all()
        if not assignments:
            raise AuthorizationDenied("Requested scope is unavailable")

        role_ids = {assignment.role_id for assignment in assignments}
        permission_rows = session.execute(
            select(RolePermission.role_id, Permission.code)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(RolePermission.role_id.in_(role_ids))
        ).all()
        permissions_by_role: dict[UUID, set[str]] = {role_id: set() for role_id in role_ids}
        for role_id, permission_code in permission_rows:
            permissions_by_role[role_id].add(permission_code)

        grants = tuple(
            ScopeGrant(
                role_id=assignment.role_id,
                entity_id=assignment.entity_id,
                module=assignment.module,
                classification_ceiling=ClassificationLevel(assignment.classification_ceiling),
                permissions=frozenset(permissions_by_role[assignment.role_id]),
            )
            for assignment in assignments
        )
        return AuthorizedScope(
            user_id=user.id,
            subject=user.subject,
            product_id=product_id,
            tenant_id=tenant_id,
            grants=grants,
        )
