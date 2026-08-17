import json
import mimetypes
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import jwt
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from attendance.config import get_settings
from attendance.db.models.identity import Entity, Product, Tenant, User
from attendance.db.models.rbac import Permission, Role, RolePermission, UserRoleAssignment
from attendance.domain.security import ClassificationLevel

SAMPLES = Path("/workspace/samples/tenant-a")
FILES = [
    "attendance.csv",
    "attendance.xlsx",
    "attendance.docx",
    "attendance-text.pdf",
    "attendance-scan.png",
    "attendance-scanned.pdf",
]


def seed_scope() -> tuple[str, str, str, str]:
    settings = get_settings()
    engine = create_engine(settings.alembic_database_url)
    subject = "synthetic-ingestion-demo"
    with Session(engine) as session:
        product = session.scalar(select(Product).where(Product.code == "ingestion-demo"))
        if product is None:
            product = Product(code="ingestion-demo", name="Synthetic Ingestion Demo")
            session.add(product)
            session.flush()
        tenant = session.scalar(
            select(Tenant).where(Tenant.product_id == product.id, Tenant.code == "tenant-a")
        )
        if tenant is None:
            tenant = Tenant(product_id=product.id, code="tenant-a", name="Fictional Tenant A")
            session.add(tenant)
            session.flush()
        entity = session.scalar(
            select(Entity).where(
                Entity.product_id == product.id,
                Entity.tenant_id == tenant.id,
                Entity.code == "head-office",
            )
        )
        if entity is None:
            entity = Entity(
                product_id=product.id,
                tenant_id=tenant.id,
                code="head-office",
                name="Fictional Head Office",
                entity_type="office",
            )
            session.add(entity)
        user = session.scalar(select(User).where(User.subject == subject))
        if user is None:
            user = User(subject=subject, display_name="Synthetic Demo User")
            session.add(user)
        session.flush()
        role = session.scalar(
            select(Role).where(
                Role.product_id == product.id,
                Role.tenant_id == tenant.id,
                Role.name == "ingestion-demo-role",
            )
        )
        if role is None:
            role = Role(
                product_id=product.id,
                tenant_id=tenant.id,
                name="ingestion-demo-role",
            )
            session.add(role)
            session.flush()
        for code in (
            "document:read",
            "document:write",
            "attendance:read",
            "attendance:write",
            "attendance:export",
            "audit:read",
            "audit:write",
            "security:context",
        ):
            permission = session.scalar(select(Permission).where(Permission.code == code))
            if permission is None:
                permission = Permission(code=code, description=f"Demo permission {code}")
                session.add(permission)
                session.flush()
            if session.get(RolePermission, (role.id, permission.id)) is None:
                session.add(RolePermission(role_id=role.id, permission_id=permission.id))
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
        result = (subject, str(product.id), str(tenant.id), str(entity.id))
    engine.dispose()
    return result


def access_token(subject: str, *, lifetime_minutes: int = 10) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": subject,
            "iat": now,
            "exp": now + timedelta(minutes=lifetime_minutes),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def main() -> None:
    subject, product_id, tenant_id, entity_id = seed_scope()
    headers = {
        "Authorization": f"Bearer {access_token(subject)}",
        "X-Product-ID": product_id,
        "X-Tenant-ID": tenant_id,
    }
    uploads: list[dict[str, object]] = []
    with httpx.Client(base_url="http://api:8000", timeout=60) as client:
        for filename in FILES:
            path = SAMPLES / filename
            media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            response = client.post(
                "/api/v1/documents",
                headers=headers,
                files={"file": (filename, path.read_bytes(), media_type)},
                data={
                    "entity_id": entity_id,
                    "module": "attendance",
                    "classification": str(int(ClassificationLevel.INTERNAL)),
                    "logical_name": f"demo-{path.stem}",
                },
            )
            response.raise_for_status()
            uploads.append({"file": filename, **response.json()})

    settings = get_settings()
    engine = create_engine(settings.alembic_database_url)
    version_ids = [upload["document_version_id"] for upload in uploads]
    with engine.connect() as connection:
        counts = (
            connection.execute(
                text(
                    "SELECT dv.source_filename, ij.status, ij.processed_units, "
                    "ij.accepted_records, ij.review_records, ij.error_count "
                    "FROM ingestion_jobs ij JOIN document_versions dv "
                    "ON dv.id = ij.document_version_id "
                    "WHERE ij.document_version_id = ANY(CAST(:version_ids AS uuid[])) "
                    "ORDER BY dv.source_filename"
                ),
                {"version_ids": version_ids},
            )
            .mappings()
            .all()
        )
        record = (
            connection.execute(
                text(
                    "SELECT ar.subject_external_id, ar.subject_display_name, ar.attendance_date, "
                    "ar.status, ar.course_or_group, ar.review_status, ar.raw_row_metadata, "
                    "eu.source_locator FROM attendance_records ar JOIN extracted_units eu "
                    "ON eu.id = ar.source_unit_id "
                    "WHERE ar.source_version_id = :version_id ORDER BY ar.attendance_date LIMIT 1"
                ),
                {"version_id": uploads[0]["document_version_id"]},
            )
            .mappings()
            .one()
        )
        ocr = (
            connection.execute(
                text(
                    "SELECT dv.source_filename, eu.extraction_confidence, eu.review_status, "
                    "eu.source_locator FROM extracted_units eu JOIN document_versions dv "
                    "ON dv.id = eu.document_version_id WHERE eu.extraction_method = 'ocr' "
                    "AND eu.document_version_id = ANY(CAST(:version_ids AS uuid[])) "
                    "ORDER BY eu.extraction_confidence LIMIT 1"
                ),
                {"version_ids": version_ids},
            )
            .mappings()
            .first()
        )
    engine.dispose()
    output = {
        "uploads": uploads,
        "counts": [dict(row) for row in counts],
        "normalized_record": dict(record),
        "source_lineage": dict(record["source_locator"]),
        "ocr_review": dict(ocr) if ocr else None,
        "run_id": str(uuid4()),
    }
    print(json.dumps(output, default=str, indent=2))


if __name__ == "__main__":
    main()
