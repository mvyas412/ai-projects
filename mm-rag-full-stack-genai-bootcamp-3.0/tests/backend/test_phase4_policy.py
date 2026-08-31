from __future__ import annotations

from collections.abc import Iterator
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.core.security import AuthenticatedIdentity, get_current_identity
from backend.app.db.base import Base
from backend.app.main import create_app
from backend.app.models import User, WorkspaceMembership, WorkspaceRole
from backend.app.services.policy import PolicyAction, PolicyService


def _identity(subject: str, email: str, name: str) -> AuthenticatedIdentity:
    return AuthenticatedIdentity(subject=subject, email=email, display_name=name)


@pytest.fixture
def client(test_settings) -> Iterator[TestClient]:
    app = create_app(test_settings)
    with TestClient(app) as test_client:
        Base.metadata.create_all(app.state.database_engine)
        app.dependency_overrides[get_current_identity] = lambda: _identity(
            "auth0|alice", "alice@example.com", "Alice"
        )
        yield test_client


def _provision(client: TestClient) -> dict:
    response = client.get("/api/v1/users/me")
    assert response.status_code == 200
    return response.json()


def _switch(client: TestClient, subject: str, email: str, name: str) -> dict:
    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_current_identity] = lambda: _identity(subject, email, name)
    return _provision(client)


def _upload(client: TestClient, workspace_id: str) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": ("policy.txt", b"policy evidence", "text/plain")},
    )
    assert response.status_code == 201
    return response.json()


def test_restricted_document_grant_and_revocation_are_immediate(client: TestClient) -> None:
    alice = _provision(client)
    workspace_id = alice["workspaces"][0]["id"]
    document = _upload(client, workspace_id)
    document_id = document["id"]

    bob = _switch(client, "auth0|bob", "bob@example.com", "Bob")
    bob_id = bob["user"]["id"]
    app = cast(FastAPI, client.app)
    with app.state.session_factory.begin() as session:
        session.add(
            WorkspaceMembership(
                workspace_id=UUID(workspace_id),
                user_id=UUID(bob_id),
                role=WorkspaceRole.MEMBER.value,
            )
        )

    _switch(client, "auth0|alice", "alice@example.com", "Alice")
    restricted = client.put(
        f"/api/v1/workspaces/{workspace_id}/access/document/{document_id}/visibility",
        json={"visibility": "restricted"},
    )
    assert restricted.status_code == 200
    assert restricted.json()["visibility"] == "restricted"

    _switch(client, "auth0|bob", "bob@example.com", "Bob")
    assert client.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}"
    ).status_code == 404
    assert client.get(f"/api/v1/workspaces/{workspace_id}/documents").json() == []

    _switch(client, "auth0|alice", "alice@example.com", "Alice")
    granted = client.put(
        f"/api/v1/workspaces/{workspace_id}/access/document/{document_id}/grants/{bob_id}"
    )
    assert granted.status_code == 200
    assert [item["principal_user_id"] for item in granted.json()["grants"]] == [bob_id]

    _switch(client, "auth0|bob", "bob@example.com", "Bob")
    assert client.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}"
    ).status_code == 200

    _switch(client, "auth0|alice", "alice@example.com", "Alice")
    assert client.delete(
        f"/api/v1/workspaces/{workspace_id}/access/document/{document_id}/grants/{bob_id}"
    ).status_code == 200
    _switch(client, "auth0|bob", "bob@example.com", "Bob")
    assert client.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}"
    ).status_code == 404


def test_new_conversations_are_creator_private_and_admin_visible(client: TestClient) -> None:
    alice = _provision(client)
    workspace_id = alice["workspaces"][0]["id"]
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/conversations",
        json={"title": "Private questions", "target_type": "workspace"},
    )
    assert created.status_code == 201
    assert created.json()["visibility"] == "restricted"

    bob = _switch(client, "auth0|bob", "bob@example.com", "Bob")
    bob_id = bob["user"]["id"]
    app = cast(FastAPI, client.app)
    with app.state.session_factory.begin() as session:
        session.add(
            WorkspaceMembership(
                workspace_id=UUID(workspace_id),
                user_id=UUID(bob_id),
                role=WorkspaceRole.ADMIN.value,
            )
        )
    listed = client.get(f"/api/v1/workspaces/{workspace_id}/conversations")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [created.json()["id"]]


@pytest.mark.parametrize(
    ("role", "action", "allowed"),
    [
        (WorkspaceRole.OWNER, PolicyAction.RETENTION_APPLY, True),
        (WorkspaceRole.ADMIN, PolicyAction.RETENTION_APPLY, False),
        (WorkspaceRole.ADMIN, PolicyAction.SECURITY_EXPORT_CREATE, True),
        (WorkspaceRole.MEMBER, PolicyAction.DOCUMENT_CREATE, True),
        (WorkspaceRole.MEMBER, PolicyAction.SECURITY_AUDIT_READ, False),
        (WorkspaceRole.VIEWER, PolicyAction.DOCUMENT_READ, True),
        (WorkspaceRole.VIEWER, PolicyAction.DOCUMENT_CREATE, False),
    ],
)
def test_policy_role_ceiling_is_default_deny(
    client: TestClient,
    role: WorkspaceRole,
    action: PolicyAction,
    allowed: bool,
) -> None:
    alice = _provision(client)
    workspace_id = UUID(alice["workspaces"][0]["id"])
    app = cast(FastAPI, client.app)
    with app.state.session_factory.begin() as session:
        user = session.scalar(select(User).where(User.external_subject == "auth0|alice"))
        assert user is not None
        membership = session.get(WorkspaceMembership, (workspace_id, user.id))
        assert membership is not None
        membership.role = role.value
    with app.state.session_factory() as session:
        user = session.scalar(select(User).where(User.external_subject == "auth0|alice"))
        assert user is not None
        policy = PolicyService(session)
        assert policy.evaluate(
            user=user, workspace_id=workspace_id, action=action
        ).allowed is allowed
        assert not policy.evaluate(
            user=user, workspace_id=workspace_id, action="unsupported.action"
        ).allowed
