from uuid import uuid4

from attendance.domain.security import AuthorizedScope, ClassificationLevel, ScopeGrant


def test_grants_cannot_combine_entity_and_classification_privileges() -> None:
    high_entity = uuid4()
    low_entity = uuid4()
    role_id = uuid4()
    scope = AuthorizedScope(
        user_id=uuid4(),
        subject="test-subject",
        product_id=uuid4(),
        tenant_id=uuid4(),
        grants=(
            ScopeGrant(
                role_id=role_id,
                entity_id=high_entity,
                module="attendance",
                classification_ceiling=ClassificationLevel.CONFIDENTIAL,
                permissions=frozenset({"attendance:read"}),
            ),
            ScopeGrant(
                role_id=role_id,
                entity_id=low_entity,
                module="attendance",
                classification_ceiling=ClassificationLevel.PUBLIC,
                permissions=frozenset({"attendance:read"}),
            ),
        ),
    )

    assert scope.permits(
        "attendance:read",
        entity_id=high_entity,
        module="attendance",
        classification=ClassificationLevel.CONFIDENTIAL,
    )
    assert not scope.permits(
        "attendance:read",
        entity_id=low_entity,
        module="attendance",
        classification=ClassificationLevel.CONFIDENTIAL,
    )
