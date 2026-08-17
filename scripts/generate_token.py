"""Generate a local demo JWT access token and print connection details.

Run inside the API container:

    docker compose run --rm api python scripts/generate_token.py

This seeds a demo user, product, tenant, entity, and role if they
do not already exist, then prints a ready-to-use bearer token along
with the product/tenant/entity IDs needed for API calls.
"""

import json
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from attendance.config import get_settings
from attendance.db.models.identity import Entity, Product, Tenant, User
from attendance.db.models.rbac import Permission, Role, RolePermission, UserRoleAssignment
from attendance.domain.security import ClassificationLevel

DEMO_SUBJECT = "demo-user"
DEMO_PERMISSIONS = (
    "document:read",
    "document:write",
    "attendance:read",
    "attendance:write",
    "attendance:export",
    "audit:read",
    "audit:write",
    "security:context",
)


def seed_demo() -> tuple[str, str, str, str]:
    """Ensure the demo user/product/tenant/entity/role exist. Returns IDs."""
    settings = get_settings()
    engine = create_engine(settings.alembic_database_url)
    with Session(engine) as session:
        # Product
        product = session.scalar(select(Product).where(Product.code == "demo"))
        if product is None:
            product = Product(code="demo", name="Demo Product")
            session.add(product)
            session.flush()

        # Tenant
        tenant = session.scalar(
            select(Tenant).where(Tenant.product_id == product.id, Tenant.code == "demo-tenant")
        )
        if tenant is None:
            tenant = Tenant(product_id=product.id, code="demo-tenant", name="Demo Tenant")
            session.add(tenant)
            session.flush()

        # Entity
        entity = session.scalar(
            select(Entity).where(
                Entity.product_id == product.id,
                Entity.tenant_id == tenant.id,
                Entity.code == "demo-entity",
            )
        )
        if entity is None:
            entity = Entity(
                product_id=product.id,
                tenant_id=tenant.id,
                code="demo-entity",
                name="Demo Entity",
                entity_type="department",
            )
            session.add(entity)

        # User
        user = session.scalar(select(User).where(User.subject == DEMO_SUBJECT))
        if user is None:
            user = User(subject=DEMO_SUBJECT, display_name="Demo User")
            session.add(user)
        session.flush()

        # Role
        role = session.scalar(
            select(Role).where(
                Role.product_id == product.id,
                Role.tenant_id == tenant.id,
                Role.name == "demo-admin",
            )
        )
        if role is None:
            role = Role(product_id=product.id, tenant_id=tenant.id, name="demo-admin")
            session.add(role)
            session.flush()

        # Permissions
        for code in DEMO_PERMISSIONS:
            permission = session.scalar(select(Permission).where(Permission.code == code))
            if permission is None:
                permission = Permission(code=code, description=f"Demo {code}")
                session.add(permission)
                session.flush()
            if session.get(RolePermission, (role.id, permission.id)) is None:
                session.add(RolePermission(role_id=role.id, permission_id=permission.id))

        # Assignment
        assignment = session.scalar(
            select(UserRoleAssignment).where(
                UserRoleAssignment.user_id == user.id,
                UserRoleAssignment.role_id == role.id,
                UserRoleAssignment.entity_id == entity.id,
                UserRoleAssignment.module == "attendance",
            )
        )
        if assignment is None:
            session.add(
                UserRoleAssignment(
                    user_id=user.id,
                    role_id=role.id,
                    product_id=product.id,
                    tenant_id=tenant.id,
                    entity_id=entity.id,
                    module="attendance",
                    classification_ceiling=int(ClassificationLevel.RESTRICTED),
                )
            )

        session.commit()
        result = (DEMO_SUBJECT, str(product.id), str(tenant.id), str(entity.id))
    engine.dispose()
    return result


def generate_token(subject: str, lifetime_hours: int = 24) -> str:
    """Create a signed JWT valid for the given number of hours."""
    settings = get_settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": subject,
            "iat": now,
            "exp": now + timedelta(hours=lifetime_hours),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def main() -> None:
    subject, product_id, tenant_id, entity_id = seed_demo()
    token = generate_token(subject, lifetime_hours=24)

    output = {
        "bearer_token": token,
        "product_id": product_id,
        "tenant_id": tenant_id,
        "entity_id": entity_id,
        "module": "attendance",
        "classification": 1,
        "expires_in": "24 hours",
        "note": "Use these values in the frontend or curl commands.",
    }
    print(json.dumps(output, indent=2))

    print("\n--- Quick test command ---")
    print(
        f'curl -s http://localhost:8000/api/v1/auth/context \\\n'
        f'  -H "Authorization: Bearer {token}" \\\n'
        f'  -H "X-Product-ID: {product_id}" \\\n'
        f'  -H "X-Tenant-ID: {tenant_id}" | python3 -m json.tool'
    )


if __name__ == "__main__":
    main()
