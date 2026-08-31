from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.core.security import AuthenticatedIdentity, get_current_identity
from backend.app.db.base import Base
from backend.app.main import create_app
from backend.app.models import (
    AuditEvent,
    Document,
    LifecycleDeletionPlan,
    LifecyclePlanState,
    OrphanObjectEvidence,
    WorkspaceMembership,
    WorkspaceRole,
)


class EmptyQdrant:
    def collection_exists(self, collection_name: str) -> bool:
        return False


class FailOnceDeleteStorage:
    def __init__(self, delegate) -> None:
        self._delegate = delegate
        self._failed = False

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    def delete(self, key: str) -> None:
        if not self._failed:
            self._failed = True
            raise RuntimeError("simulated unavailable store")
        self._delegate.delete(key)


def _identity(subject: str, email: str, name: str) -> AuthenticatedIdentity:
    return AuthenticatedIdentity(subject=subject, email=email, display_name=name)


@pytest.fixture
def client(test_settings) -> Iterator[TestClient]:
    app = create_app(test_settings)
    with TestClient(app) as test_client:
        Base.metadata.create_all(app.state.database_engine)
        app.state.qdrant_client = EmptyQdrant()
        app.dependency_overrides[get_current_identity] = lambda: _identity(
            "auth0|lifecycle-owner", "owner@example.com", "Owner"
        )
        yield test_client


def _me(client: TestClient) -> dict:
    response = client.get("/api/v1/users/me")
    assert response.status_code == 200
    return response.json()


def _switch(client: TestClient, subject: str, email: str, name: str) -> dict:
    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_current_identity] = lambda: _identity(subject, email, name)
    return _me(client)


def _upload(client: TestClient, workspace_id: str) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": ("governed.txt", b"governed content", "text/plain")},
    )
    assert response.status_code == 201
    return response.json()


def test_document_tombstone_is_immediate_recoverable_and_owner_only(
    client: TestClient,
) -> None:
    owner = _me(client)
    workspace_id = owner["workspaces"][0]["id"]
    document = _upload(client, workspace_id)

    member = _switch(client, "auth0|lifecycle-member", "member@example.com", "Member")
    app = cast(FastAPI, client.app)
    with app.state.session_factory.begin() as session:
        session.add(
            WorkspaceMembership(
                workspace_id=UUID(workspace_id),
                user_id=UUID(member["user"]["id"]),
                role=WorkspaceRole.MEMBER.value,
            )
        )
    denied = client.post(
        f"/api/v1/workspaces/{workspace_id}/governance/documents/"
        f"{document['id']}/deletion"
    )
    assert denied.status_code == 403

    _switch(client, "auth0|lifecycle-owner", "owner@example.com", "Owner")
    requested = client.post(
        f"/api/v1/workspaces/{workspace_id}/governance/documents/"
        f"{document['id']}/deletion"
    )
    assert requested.status_code == 202
    assert requested.json()["state"] == LifecyclePlanState.RECOVERABLE.value
    assert client.get(f"/api/v1/workspaces/{workspace_id}/documents").json() == []
    assert client.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{document['id']}"
    ).status_code == 404

    restored = client.post(
        f"/api/v1/workspaces/{workspace_id}/governance/documents/"
        f"{document['id']}/restore"
    )
    assert restored.status_code == 204
    assert len(client.get(f"/api/v1/workspaces/{workspace_id}/documents").json()) == 1


def test_due_document_purge_reconciles_objects_and_metadata(client: TestClient) -> None:
    owner = _me(client)
    workspace_id = owner["workspaces"][0]["id"]
    document = _upload(client, workspace_id)
    plan = client.post(
        f"/api/v1/workspaces/{workspace_id}/governance/documents/"
        f"{document['id']}/deletion"
    ).json()
    app = cast(FastAPI, client.app)
    with app.state.session_factory.begin() as session:
        stored = session.get(LifecycleDeletionPlan, UUID(plan["id"]))
        assert stored is not None
        stored.execute_after = datetime.now(UTC) - timedelta(seconds=1)

    preview = client.get(
        f"/api/v1/workspaces/{workspace_id}/governance/retention/preview"
    )
    assert preview.status_code == 200
    assert preview.json()["due_document_deletions"] == 1
    applied = client.post(
        f"/api/v1/workspaces/{workspace_id}/governance/retention/apply",
        json={"preview_token": preview.json()["preview_token"]},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["completed_plans"] == 1
    assert applied.json()["blocked_plans"] == 0

    with app.state.session_factory() as session:
        assert session.get(Document, UUID(document["id"])) is None
        stored = session.get(LifecycleDeletionPlan, UUID(plan["id"]))
        assert stored is not None
        assert stored.state == LifecyclePlanState.COMPLETED.value
        actions = set(
            session.scalars(
                select(AuditEvent.action).where(
                    AuditEvent.workspace_id == UUID(workspace_id)
                )
            )
        )
        assert "lifecycle.document_purged" in actions


def test_hold_blocks_preview_until_admin_removes_it(client: TestClient) -> None:
    owner = _me(client)
    workspace_id = owner["workspaces"][0]["id"]
    document = _upload(client, workspace_id)
    hold_url = (
        f"/api/v1/workspaces/{workspace_id}/governance/holds/document/{document['id']}"
    )
    placed = client.put(hold_url, json={"reason_code": "incident.review"})
    assert placed.status_code == 200
    blocked = client.post(
        f"/api/v1/workspaces/{workspace_id}/governance/documents/"
        f"{document['id']}/deletion"
    )
    assert blocked.status_code == 409
    assert client.delete(hold_url).status_code == 204
    assert client.post(
        f"/api/v1/workspaces/{workspace_id}/governance/documents/"
        f"{document['id']}/deletion"
    ).status_code == 202


def test_orphan_inventory_requires_an_aged_rechecked_identity_before_cleanup(
    client: TestClient,
) -> None:
    owner = _me(client)
    workspace_id = owner["workspaces"][0]["id"]
    app = cast(FastAPI, client.app)
    orphan_key = f"workspaces/{workspace_id}/failed/intake/original"
    app.state.object_storage.put(orphan_key, b"orphan", media_type="text/plain")

    inventory = client.post(
        f"/api/v1/workspaces/{workspace_id}/governance/retention/orphan-inventory"
    )
    assert inventory.status_code == 200
    assert inventory.json()["orphan_objects"] == 1
    assert inventory.json()["new_evidence"] == 1
    with app.state.session_factory.begin() as session:
        evidence = session.scalar(
            select(OrphanObjectEvidence).where(
                OrphanObjectEvidence.workspace_id == UUID(workspace_id)
            )
        )
        assert evidence is not None
        evidence.first_seen_at = datetime.now(UTC) - timedelta(days=8)

    preview = client.get(
        f"/api/v1/workspaces/{workspace_id}/governance/retention/preview"
    )
    assert preview.status_code == 200
    assert preview.json()["orphan_objects"] == 1
    applied = client.post(
        f"/api/v1/workspaces/{workspace_id}/governance/retention/apply",
        json={"preview_token": preview.json()["preview_token"]},
    )
    assert applied.status_code == 200
    assert applied.json()["deleted_orphan_objects"] == 1
    assert not app.state.object_storage.exists(orphan_key)


def test_partial_cross_store_failure_resumes_from_durable_checkpoints(
    client: TestClient,
) -> None:
    owner = _me(client)
    workspace_id = owner["workspaces"][0]["id"]
    document = _upload(client, workspace_id)
    app = cast(FastAPI, client.app)
    stable_storage = app.state.object_storage
    app.state.object_storage = FailOnceDeleteStorage(stable_storage)
    plan = client.post(
        f"/api/v1/workspaces/{workspace_id}/governance/documents/"
        f"{document['id']}/deletion"
    ).json()
    with app.state.session_factory.begin() as session:
        stored = session.get(LifecycleDeletionPlan, UUID(plan["id"]))
        assert stored is not None
        stored.execute_after = datetime.now(UTC) - timedelta(seconds=1)

    first_preview = client.get(
        f"/api/v1/workspaces/{workspace_id}/governance/retention/preview"
    ).json()
    first_apply = client.post(
        f"/api/v1/workspaces/{workspace_id}/governance/retention/apply",
        json={"preview_token": first_preview["preview_token"]},
    )
    assert first_apply.status_code == 200
    assert first_apply.json()["blocked_plans"] == 1
    with app.state.session_factory() as session:
        blocked = session.get(LifecycleDeletionPlan, UUID(plan["id"]))
        assert blocked is not None
        assert blocked.vectors_deleted_at is not None
        assert blocked.artifacts_deleted_at is not None
        assert blocked.originals_deleted_at is None

    app.state.object_storage = stable_storage
    second_preview = client.get(
        f"/api/v1/workspaces/{workspace_id}/governance/retention/preview"
    ).json()
    second_apply = client.post(
        f"/api/v1/workspaces/{workspace_id}/governance/retention/apply",
        json={"preview_token": second_preview["preview_token"]},
    )
    assert second_apply.status_code == 200
    assert second_apply.json()["completed_plans"] == 1
