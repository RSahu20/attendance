import json
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from attendance.audit.service import append_audit_event
from attendance.db.rls import set_authorization_context
from attendance.domain.security import ClassificationLevel
from attendance.security.authentication import Principal
from attendance.security.authorization import AuthorizationService
from tests.integration.conftest import SecuritySeed


@pytest.mark.integration
def test_runtime_database_role_cannot_bypass_rls_or_own_protected_tables(
    migration_database_url: str, runtime_database_user: str
) -> None:
    engine = create_engine(migration_database_url)
    try:
        with engine.connect() as connection:
            role_flags = connection.execute(
                text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = :role_name"),
                {"role_name": runtime_database_user},
            ).one()
            audit_owner = connection.scalar(
                text(
                    """
                    SELECT owner.rolname
                    FROM pg_class table_info
                    JOIN pg_roles owner ON owner.oid = table_info.relowner
                    WHERE table_info.oid = 'audit_events'::regclass
                    """
                )
            )
    finally:
        engine.dispose()

    assert role_flags == (False, False)
    assert audit_owner != runtime_database_user


@pytest.mark.integration
def test_audit_table_has_rls_policies(database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            rls_enabled = connection.scalar(
                text("SELECT relrowsecurity FROM pg_class WHERE oid = 'audit_events'::regclass")
            )
            policies = connection.scalar(
                text("SELECT count(*) FROM pg_policies WHERE tablename = 'audit_events'")
            )
    finally:
        engine.dispose()

    assert rls_enabled is True
    assert policies == 2


@pytest.mark.integration
def test_runtime_role_can_write_and_read_only_with_authorized_rls_context(
    database_url: str, security_seed: SecuritySeed
) -> None:
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            scope = AuthorizationService().resolve_scope(
                session,
                Principal(subject=security_seed.subject),
                product_id=security_seed.product_id,
                tenant_id=security_seed.tenant_a_id,
            )
            set_authorization_context(session, scope)
            event = append_audit_event(
                session,
                scope,
                action="test.read",
                resource_type="test",
                outcome="allowed",
                entity_id=security_seed.entity_high_id,
                module="attendance",
                classification=ClassificationLevel.PUBLIC,
            )
            session.flush()
            event_id = event.id

            visible_id = session.scalar(
                text("SELECT id FROM audit_events WHERE id = :id"), {"id": event_id}
            )
            session.rollback()
    finally:
        engine.dispose()

    assert visible_id == event_id


@pytest.mark.integration
def test_runtime_role_cannot_read_audit_event_without_rls_context(
    migration_database_url: str,
    runtime_database_user: str,
    security_seed: SecuritySeed,
) -> None:
    engine = create_engine(migration_database_url)
    connection = engine.connect()
    transaction = connection.begin()
    event_id = uuid4()
    try:
        connection.execute(
            text(
                """
                INSERT INTO audit_events (
                    id, request_id, actor_user_id, product_id, tenant_id, entity_id,
                    module, classification, role_ids, action, resource_type, outcome, metadata
                ) VALUES (
                    :id, :request_id, :actor_user_id, :product_id, :tenant_id, :entity_id,
                    'attendance', 0, '[]'::jsonb, 'test.read', 'test', 'allowed', '{}'::jsonb
                )
                """
            ),
            {
                "id": event_id,
                "request_id": uuid4(),
                "actor_user_id": security_seed.user_id,
                "product_id": security_seed.product_id,
                "tenant_id": security_seed.tenant_a_id,
                "entity_id": security_seed.entity_high_id,
            },
        )
        connection.execute(
            text("SELECT set_config('role', :role_name, true)"),
            {"role_name": runtime_database_user},
        )

        without_scope = connection.scalar(
            text("SELECT count(*) FROM audit_events WHERE id = :id"), {"id": event_id}
        )

        grants = json.dumps(
            [
                {
                    "entity_id": str(security_seed.entity_high_id),
                    "module": "attendance",
                    "classification_ceiling": 0,
                    "permissions": ["audit:read"],
                }
            ]
        )
        connection.execute(
            text(
                """
                SELECT
                    set_config('app.product_id', :product_id, true),
                    set_config('app.tenant_id', :tenant_id, true),
                    set_config('app.authorization_grants', :grants, true)
                """
            ),
            {
                "product_id": str(security_seed.product_id),
                "tenant_id": str(security_seed.tenant_a_id),
                "grants": grants,
            },
        )
        with_scope = connection.scalar(
            text("SELECT count(*) FROM audit_events WHERE id = :id"), {"id": event_id}
        )
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()

    assert without_scope == 0
    assert with_scope == 1


@pytest.mark.integration
def test_audit_events_are_append_only(
    migration_database_url: str, security_seed: SecuritySeed
) -> None:
    engine = create_engine(migration_database_url)
    connection = engine.connect()
    transaction = connection.begin()
    event_id = uuid4()
    try:
        connection.execute(
            text(
                """
                INSERT INTO audit_events (
                    id, request_id, actor_user_id, product_id, tenant_id, entity_id,
                    module, classification, role_ids, action, resource_type, outcome, metadata
                ) VALUES (
                    :id, :request_id, :actor_user_id, :product_id, :tenant_id, :entity_id,
                    'attendance', 0, '[]'::jsonb, 'test.read', 'test', 'allowed', '{}'::jsonb
                )
                """
            ),
            {
                "id": event_id,
                "request_id": uuid4(),
                "actor_user_id": security_seed.user_id,
                "product_id": security_seed.product_id,
                "tenant_id": security_seed.tenant_a_id,
                "entity_id": security_seed.entity_high_id,
            },
        )

        with pytest.raises(DBAPIError, match="append-only"):
            connection.execute(
                text("UPDATE audit_events SET outcome = 'changed' WHERE id = :id"),
                {"id": event_id},
            )
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()
