from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.exc import DBAPIError

from backend.app.core.config import get_settings
from backend.app.core.security import AuthenticatedIdentity, get_current_identity
from backend.app.db.base import Base
from backend.app.db.rls import DatabasePurpose, set_rls_context
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.main import create_app
from backend.app.models import (
    AuditEvent,
    ResourceVisibility,
    User,
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
)
from backend.app.services.audit import (
    AuditValidationError,
    record_audit_event,
    validate_audit_details,
)
from backend.app.services.policy import (
    PolicyAction,
    PolicyDeniedError,
    PolicyService,
)


def _identity(subject: str, email: str, name: str) -> AuthenticatedIdentity:
    return AuthenticatedIdentity(subject=subject, email=email, display_name=name)


@pytest.fixture
def client(test_settings) -> Iterator[TestClient]:
    app = create_app(test_settings)
    with TestClient(app) as test_client:
        Base.metadata.create_all(app.state.database_engine)
        app.dependency_overrides[get_current_identity] = lambda: _identity(
            "auth0|audit-owner", "owner@example.com", "Owner"
        )
        yield test_client


def _switch(client: TestClient, subject: str, email: str, name: str) -> dict:
    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_current_identity] = lambda: _identity(subject, email, name)
    response = client.get("/api/v1/users/me")
    assert response.status_code == 200
    return response.json()


def _owner(client: TestClient) -> dict:
    response = client.get("/api/v1/users/me")
    assert response.status_code == 200
    return response.json()


def test_security_view_is_owner_admin_only_and_records_the_read(client: TestClient) -> None:
    owner = _owner(client)
    workspace_id = owner["workspaces"][0]["id"]
    upload = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": ("audit.txt", b"safe evidence", "text/plain")},
    )
    assert upload.status_code == 201

    response = client.get(
        f"/api/v1/workspaces/{workspace_id}/security/audit-events",
        params={"action": "document.created"},
    )
    assert response.status_code == 200
    assert [event["action"] for event in response.json()] == ["document.created"]
    assert response.json()[0]["actor_kind"] == "user"
    assert response.json()[0]["result"] == "succeeded"
    assert response.json()[0]["policy_revision"] == "phase4-v1"

    bob = _switch(client, "auth0|audit-bob", "bob@example.com", "Bob")
    app = cast(FastAPI, client.app)
    with app.state.session_factory.begin() as session:
        session.add(
            WorkspaceMembership(
                workspace_id=UUID(workspace_id),
                user_id=UUID(bob["user"]["id"]),
                role=WorkspaceRole.MEMBER.value,
            )
        )
    assert client.get(
        f"/api/v1/workspaces/{workspace_id}/security/audit-events"
    ).status_code == 403
    with app.state.session_factory.begin() as session:
        membership = session.get(
            WorkspaceMembership,
            (UUID(workspace_id), UUID(bob["user"]["id"])),
        )
        assert membership is not None
        membership.role = WorkspaceRole.ADMIN.value
    assert client.get(
        f"/api/v1/workspaces/{workspace_id}/security/audit-events",
        params={"action": "security.audit_viewed"},
    ).status_code == 200

    _switch(client, "auth0|audit-outsider", "out@example.com", "Outsider")
    assert client.get(
        f"/api/v1/workspaces/{workspace_id}/security/audit-events"
    ).status_code == 404


def test_compliance_export_is_bounded_checksummed_reproducible_and_audited(
    client: TestClient,
) -> None:
    owner = _owner(client)
    workspace_id = owner["workspaces"][0]["id"]
    assert client.post(
        f"/api/v1/workspaces/{workspace_id}/collections",
        json={"name": "Export evidence"},
    ).status_code == 201
    range_start = datetime.now(UTC) - timedelta(days=1)
    range_end = datetime.now(UTC)
    payload = {
        "range_start": range_start.isoformat(),
        "range_end": range_end.isoformat(),
    }

    first = client.post(
        f"/api/v1/workspaces/{workspace_id}/security/compliance-exports",
        json=payload,
    )
    assert first.status_code == 201
    metadata = first.json()
    assert metadata["status"] == "ready"
    assert metadata["schema_version"] == 1
    assert "object_key" not in first.text
    content = client.get(
        f"/api/v1/workspaces/{workspace_id}/security/compliance-exports/"
        f"{metadata['id']}/content"
    )
    assert content.status_code == 200
    assert hashlib.sha256(content.content).hexdigest() == metadata["content_sha256"]
    exported = json.loads(content.content)
    assert exported["schema_version"] == 1
    assert exported["workspace_id"] == workspace_id
    assert exported["events"]
    assert "token" not in content.text.lower()
    assert "object_key" not in content.text

    replay = client.post(
        f"/api/v1/workspaces/{workspace_id}/security/compliance-exports",
        json=payload,
    )
    assert replay.status_code == 201
    assert replay.json()["content_sha256"] == metadata["content_sha256"]

    app = cast(FastAPI, client.app)
    with app.state.session_factory() as session:
        actions = set(
            session.scalars(
                select(AuditEvent.action).where(
                    AuditEvent.workspace_id == UUID(workspace_id)
                )
            )
        )
    assert {"security.export_created", "security.export_downloaded"} <= actions

    too_large = client.post(
        f"/api/v1/workspaces/{workspace_id}/security/compliance-exports",
        json={
            "range_start": (datetime.now(UTC) - timedelta(days=32)).isoformat(),
            "range_end": datetime.now(UTC).isoformat(),
        },
    )
    assert too_large.status_code == 422


@pytest.mark.parametrize(
    "details",
    [
        {"token": "secret"},
        {"content": "document text"},
        {"title": "unnecessary sensitive title"},
        {"job_id": "x" * 256},
        {"job_id": ["nested", "data"]},
    ],
)
def test_audit_details_reject_secret_content_unknown_and_oversized_fields(
    details: dict[str, object],
) -> None:
    with pytest.raises(AuditValidationError):
        validate_audit_details(details)


def test_privileged_policy_mutation_rolls_back_when_audit_write_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = _owner(client)
    workspace_id = owner["workspaces"][0]["id"]
    document = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": ("rollback.txt", b"rollback", "text/plain")},
    ).json()

    def fail_audit(*args, **kwargs):
        raise AuditValidationError

    monkeypatch.setattr("backend.app.services.access.record_audit_event", fail_audit)
    with pytest.raises(AuditValidationError):
        client.put(
            f"/api/v1/workspaces/{workspace_id}/access/document/"
            f"{document['id']}/visibility",
            json={"visibility": "restricted"},
        )
    access = client.get(
        f"/api/v1/workspaces/{workspace_id}/access/document/{document['id']}"
    )
    assert access.status_code == 200
    assert access.json()["visibility"] == ResourceVisibility.WORKSPACE.value


def test_denial_remains_denied_when_best_effort_audit_is_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = _owner(client)
    workspace_id = owner["workspaces"][0]["id"]
    member = _switch(client, "auth0|denied-member", "member@example.com", "Member")
    app = cast(FastAPI, client.app)
    with app.state.session_factory.begin() as session:
        session.add(
            WorkspaceMembership(
                workspace_id=UUID(workspace_id),
                user_id=UUID(member["user"]["id"]),
                role=WorkspaceRole.MEMBER.value,
            )
        )

    def fail_audit(*args: object, **kwargs: object) -> None:
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(PolicyService, "_record_denial_best_effort", fail_audit)
    response = client.get(
        f"/api/v1/workspaces/{workspace_id}/security/audit-events"
    )
    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("MM_RAG_RUN_INTEGRATION_TESTS") != "1",
    reason="Set MM_RAG_RUN_INTEGRATION_TESTS=1 with PostgreSQL running",
)
def test_postgres_api_role_cannot_update_or_delete_audit_events() -> None:
    engine = create_database_engine(get_settings())
    factory = create_session_factory(engine)
    user_id, member_id, workspace_id = uuid4(), uuid4(), uuid4()
    event_id = None
    try:
        with factory.begin() as session:
            session.add_all(
                [
                    User(id=user_id, external_subject=f"test|audit-{user_id}"),
                    User(id=member_id, external_subject=f"test|audit-{member_id}"),
                ]
            )
            session.flush()
            session.add(
                Workspace(
                    id=workspace_id,
                    name="Audit append only",
                    created_by_user_id=user_id,
                )
            )
            session.flush()
            session.add(
                WorkspaceMembership(
                    workspace_id=workspace_id,
                    user_id=user_id,
                    role=WorkspaceRole.OWNER.value,
                )
            )
            session.add(
                WorkspaceMembership(
                    workspace_id=workspace_id,
                    user_id=member_id,
                    role=WorkspaceRole.MEMBER.value,
                )
            )
            event_id = record_audit_event(
                session,
                workspace_id=workspace_id,
                actor_user_id=user_id,
                action="security.fixture_created",
                resource_type="workspace",
                resource_id=workspace_id,
            ).id

        with factory() as session:
            member = session.get(User, member_id)
            assert member is not None
            with pytest.raises(PolicyDeniedError):
                PolicyService(session).require(
                    user=member,
                    workspace_id=workspace_id,
                    action=PolicyAction.SECURITY_AUDIT_READ,
                )
            session.rollback()
        with factory() as session:
            denied = session.scalar(
                select(AuditEvent).where(
                    AuditEvent.workspace_id == workspace_id,
                    AuditEvent.action == "policy.denied",
                    AuditEvent.actor_user_id == member_id,
                )
            )
            assert denied is not None
            assert denied.result == "denied"
            assert denied.details["requested_action"] == "security.audit.read"

        with pytest.raises(DBAPIError):
            with factory.begin() as session:
                set_rls_context(
                    session,
                    purpose=DatabasePurpose.API,
                    workspace_id=workspace_id,
                    principal_id=user_id,
                )
                event = session.get(AuditEvent, event_id)
                assert event is not None
                event.result = "failed"
                session.flush()

        with pytest.raises(DBAPIError):
            with factory.begin() as session:
                set_rls_context(
                    session,
                    purpose=DatabasePurpose.API,
                    workspace_id=workspace_id,
                    principal_id=user_id,
                )
                session.execute(delete(AuditEvent).where(AuditEvent.id == event_id))
    finally:
        with factory.begin() as session:
            session.execute(delete(AuditEvent).where(AuditEvent.id == event_id))
            session.execute(
                delete(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id == workspace_id
                )
            )
            session.execute(delete(Workspace).where(Workspace.id == workspace_id))
            session.execute(delete(User).where(User.id.in_([user_id, member_id])))
        engine.dispose()
