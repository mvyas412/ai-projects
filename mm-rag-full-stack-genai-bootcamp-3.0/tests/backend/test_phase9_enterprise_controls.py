import hashlib
import hmac
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.models import RetentionHold, User, Workspace, WorkspaceMembership
from backend.app.services.billing import BillingEventError, SimulatedBillingService
from backend.app.services.compliance_admin import (
    ComplianceAdminService,
    ComplianceScopeChangedError,
)
from backend.app.services.enterprise_identity import (
    EnterpriseIdentityConflictError,
    EnterpriseIdentityService,
)
from backend.app.services.policy import PolicyAction, PolicyService
from backend.app.services.usage import QuotaExceededError, UsageLedgerService


@pytest.fixture
def enterprise_session() -> Iterator[tuple[Session, User, Workspace]]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    user = User(external_subject=f"test|{uuid4()}")
    session.add(user)
    session.flush()
    workspace = Workspace(name="Enterprise", created_by_user_id=user.id)
    session.add(workspace)
    session.flush()
    session.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role="owner"))
    session.commit()
    yield session, user, workspace
    session.close()


def test_scim_lifecycle_is_ordered_and_suspension_denies_access(enterprise_session) -> None:
    session, user, workspace = enterprise_session
    identities = EnterpriseIdentityService(session)
    identity = identities.apply_user(
        workspace_id=workspace.id,
        user=user,
        provider="test-scim",
        external_id="opaque-employee-id",
        sequence=1,
        active=True,
    )
    assert (
        PolicyService(session)
        .evaluate(user=user, workspace_id=workspace.id, action=PolicyAction.WORKSPACE_VIEW)
        .allowed
    )

    identities.apply_user(
        workspace_id=workspace.id,
        user=user,
        provider="test-scim",
        external_id="opaque-employee-id",
        sequence=2,
        active=False,
    )
    decision = PolicyService(session).evaluate(
        user=user, workspace_id=workspace.id, action=PolicyAction.WORKSPACE_VIEW
    )
    assert not decision.allowed
    assert decision.reason == "enterprise_identity_inactive"
    with pytest.raises(EnterpriseIdentityConflictError, match="stale"):
        identities.apply_user(
            workspace_id=workspace.id,
            user=user,
            provider="test-scim",
            external_id=identity.external_id,
            sequence=1,
            active=True,
        )


def test_group_mapping_rejects_role_above_central_ceiling(enterprise_session) -> None:
    session, _, workspace = enterprise_session
    identities = EnterpriseIdentityService(session)

    with pytest.raises(EnterpriseIdentityConflictError, match="not allowed"):
        identities.map_group(
            workspace_id=workspace.id,
            provider="test-scim",
            external_group_id="group-1",
            role="owner",
        )


def test_usage_reservation_settlement_and_additive_correction(enterprise_session) -> None:
    session, _, workspace = enterprise_session
    usage = UsageLedgerService(session)
    now = datetime(2026, 9, 19, 20, 0, tzinfo=UTC)
    reservation = usage.reserve(
        workspace_id=workspace.id,
        idempotency_key="request-1",
        meter="test.questions",
        quantity=3,
        quota=5,
        expires_at=now + timedelta(minutes=5),
    )
    with pytest.raises(QuotaExceededError):
        usage.reserve(
            workspace_id=workspace.id,
            idempotency_key="request-2",
            meter="test.questions",
            quantity=3,
            quota=5,
            expires_at=now + timedelta(minutes=5),
        )
    entry = usage.settle(
        workspace_id=workspace.id,
        reservation_id=reservation.id,
        actual_quantity=2,
        meter_version=1,
        unit="question",
        resource_type="conversation",
        resource_id=None,
        occurred_at=now,
    )
    correction = usage.correct(
        workspace_id=workspace.id,
        original_entry_id=entry.id,
        idempotency_key="correction-1",
        quantity=-1,
        occurred_at=now,
    )

    assert entry.quantity == 2
    assert correction.quantity == -1
    assert correction.correction_of_id == entry.id


def test_simulated_billing_verifies_signature_and_is_idempotent(enterprise_session) -> None:
    session, _, workspace = enterprise_session
    secret = b"test-only-secret"
    service = SimulatedBillingService(session, secret)
    body = json.dumps(
        {
            "event_id": "evt-1",
            "event_type": "subscription.updated",
            "workspace_id": str(workspace.id),
            "entitlement_version": 1,
            "rules": {"learning": True},
        },
        sort_keys=True,
    ).encode()
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    now = datetime(2026, 9, 19, 20, 0, tzinfo=UTC)

    event = service.ingest(body, signature, received_at=now)
    assert service.ingest(body, signature, received_at=now).id == event.id
    policy = service.process(event, body, now=now)

    assert policy.rules == {"learning": True}
    assert event.state == "processed"
    with pytest.raises(BillingEventError, match="signature"):
        service.ingest(body, "invalid", received_at=now)


def test_compliance_requires_stable_scope_and_hold_blocks_apply(enterprise_session) -> None:
    session, user, workspace = enterprise_session
    service = ComplianceAdminService(session)
    resource_id = uuid4()
    now = datetime(2026, 9, 19, 20, 0, tzinfo=UTC)
    workflow = service.preview(
        workspace_id=workspace.id,
        requested_by_user_id=user.id,
        operation="tenant_export",
        reason_code="learning_proof",
        idempotency_key="workflow-1",
        policy_revision="phase9-v1",
        resource_ids=(resource_id,),
    )
    with pytest.raises(ComplianceScopeChangedError):
        service.authorize(
            workflow_id=workflow.id,
            workspace_id=workspace.id,
            authorized_by_user_id=user.id,
            resource_ids=(uuid4(),),
            now=now,
        )
    service.authorize(
        workflow_id=workflow.id,
        workspace_id=workspace.id,
        authorized_by_user_id=user.id,
        resource_ids=(resource_id,),
        now=now,
    )
    session.add(
        RetentionHold(
            workspace_id=workspace.id,
            resource_type="document",
            resource_id=resource_id,
            placed_by_user_id=user.id,
            reason_code="legal_hold",
        )
    )
    session.flush()

    result = service.complete(
        workflow_id=workflow.id,
        workspace_id=workspace.id,
        resource_ids=(resource_id,),
        deleted_counts={"sql": 0},
        now=now,
    )
    assert result.state == "blocked"
    assert result.evidence_manifest is None
