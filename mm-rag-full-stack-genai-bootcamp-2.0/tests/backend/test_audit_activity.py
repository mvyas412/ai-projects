from collections.abc import Iterator
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.core.security import AuthenticatedIdentity, get_current_identity
from backend.app.db.base import Base
from backend.app.main import create_app
from backend.app.models import AuditEvent
from backend.app.rag.indexing import IndexingRequest, IndexingResult


class FakeIndexer:
    def index(self, request: IndexingRequest) -> IndexingResult:
        return IndexingResult(chunk_count=2)


@pytest.fixture
def client(test_settings) -> Iterator[TestClient]:
    app = create_app(test_settings)
    with TestClient(app) as test_client:
        Base.metadata.create_all(app.state.database_engine)
        app.dependency_overrides[get_current_identity] = lambda: AuthenticatedIdentity(
            subject="auth0|alice",
            email="alice@example.com",
            display_name="Alice",
        )
        app.state.document_indexer = FakeIndexer()
        yield test_client


def test_activity_records_principal_document_actions(client: TestClient) -> None:
    profile = client.get("/api/v1/users/me").json()
    workspace_id = profile["workspaces"][0]["id"]
    uploaded = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": ("evidence.txt", b"Grounded evidence", "text/plain")},
    )
    assert uploaded.status_code == 201
    document_id = uploaded.json()["id"]
    version_id = uploaded.json()["latest_version"]["id"]
    assert client.post(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/versions/"
        f"{version_id}/index"
    ).status_code == 200
    assert client.post(
        f"/api/v1/workspaces/{workspace_id}/collections",
        json={"name": "Evidence set"},
    ).status_code == 201

    response = client.get(f"/api/v1/workspaces/{workspace_id}/activity")
    assert response.status_code == 200
    events = response.json()
    actions = {event["action"] for event in events}
    assert {
        "workspace.provisioned",
        "document.created",
        "document.version_indexed",
        "collection.created",
    } <= actions
    assert all(event["actor_display_name"] == "Alice" for event in events)
    assert all(event["actor_user_id"] == profile["user"]["id"] for event in events)
    assert all("token" not in str(event["details"]).lower() for event in events)

    app = cast(FastAPI, client.app)
    with app.state.session_factory() as session:
        persisted = list(session.scalars(select(AuditEvent)))
        assert len(persisted) == len(events)


def test_activity_is_workspace_scoped_and_non_enumerating(client: TestClient) -> None:
    workspace_id = client.get("/api/v1/users/me").json()["workspaces"][0]["id"]
    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_current_identity] = lambda: AuthenticatedIdentity(
        subject="auth0|bob",
        email="bob@example.com",
        display_name="Bob",
    )
    assert client.get(f"/api/v1/workspaces/{workspace_id}/activity").status_code == 404


def test_activity_limit_is_bounded(client: TestClient) -> None:
    workspace_id = client.get("/api/v1/users/me").json()["workspaces"][0]["id"]
    assert client.get(
        f"/api/v1/workspaces/{workspace_id}/activity", params={"limit": 0}
    ).status_code == 422
    assert client.get(
        f"/api/v1/workspaces/{workspace_id}/activity", params={"limit": 201}
    ).status_code == 422
