from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from attendance.db.models.identity import Entity, Product, Tenant, User
from attendance.db.models.rbac import Permission, Role, RolePermission, UserRoleAssignment
from attendance.domain.security import ClassificationLevel


@dataclass(frozen=True)
class SecuritySeed:
    subject: str
    user_id: UUID
    product_id: UUID
    tenant_a_id: UUID
    tenant_b_id: UUID
    entity_high_id: UUID
    entity_low_id: UUID


@pytest.fixture
def security_seed(database_url: str) -> Iterator[SecuritySeed]:
    engine = create_engine(database_url, pool_pre_ping=True)
    subject = f"security-test-{uuid4()}"
    permission_ids: list[UUID] = []

    with Session(engine) as session:
        product = Product(code=f"product-{uuid4()}", name="Security Test Product")
        tenant_a = Tenant(product=product, code=f"tenant-a-{uuid4()}", name="Tenant A")
        tenant_b = Tenant(product=product, code=f"tenant-b-{uuid4()}", name="Tenant B")
        user = User(subject=subject, email=None, display_name="Security Test User")
        session.add_all([product, tenant_a, tenant_b, user])
        session.flush()

        entity_high = Entity(
            product_id=product.id,
            tenant_id=tenant_a.id,
            code=f"entity-high-{uuid4()}",
            name="High Entity",
            entity_type="department",
        )
        entity_low = Entity(
            product_id=product.id,
            tenant_id=tenant_a.id,
            code=f"entity-low-{uuid4()}",
            name="Low Entity",
            entity_type="department",
        )
        role = Role(
            product_id=product.id,
            tenant_id=tenant_a.id,
            name=f"reader-{uuid4()}",
        )
        permission_specs = {
            "security:context": "Test context access",
            "attendance:read": "Test attendance read",
            "audit:read": "Test audit read",
            "audit:write": "Test audit write",
            "document:read": "Test document read",
            "document:write": "Test document write",
            "attendance:write": "Test attendance write",
            "attendance:export": "Test attendance export",
        }
        permissions = []
        session.add_all([entity_high, entity_low, role])
        for code, description in permission_specs.items():
            permission = session.scalar(select(Permission).where(Permission.code == code))
            if permission is None:
                permission = Permission(code=code, description=description)
                session.add(permission)
                session.flush()
                permission_ids.append(permission.id)
            permissions.append(permission)
        session.flush()
        session.add_all(
            [
                RolePermission(role_id=role.id, permission_id=permission.id)
                for permission in permissions
            ]
        )
        session.add_all(
            [
                UserRoleAssignment(
                    user_id=user.id,
                    role_id=role.id,
                    product_id=product.id,
                    tenant_id=tenant_a.id,
                    entity_id=entity_high.id,
                    module="attendance",
                    classification_ceiling=int(ClassificationLevel.CONFIDENTIAL),
                ),
                UserRoleAssignment(
                    user_id=user.id,
                    role_id=role.id,
                    product_id=product.id,
                    tenant_id=tenant_a.id,
                    entity_id=entity_low.id,
                    module="attendance",
                    classification_ceiling=int(ClassificationLevel.PUBLIC),
                ),
            ]
        )
        session.commit()
        seed = SecuritySeed(
            subject=subject,
            user_id=user.id,
            product_id=product.id,
            tenant_a_id=tenant_a.id,
            tenant_b_id=tenant_b.id,
            entity_high_id=entity_high.id,
            entity_low_id=entity_low.id,
        )

    try:
        yield seed
    finally:
        with Session(engine) as session:
            session.execute(delete(Product).where(Product.id == seed.product_id))
            session.execute(delete(User).where(User.id == seed.user_id))
            session.execute(delete(Permission).where(Permission.id.in_(permission_ids)))
            session.commit()
        engine.dispose()
