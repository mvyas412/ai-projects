from __future__ import annotations

from collections.abc import Iterator
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.core.security import AuthenticatedIdentity, get_current_identity
from backend.app.db.base import Base
from backend.app.main import create_app
from backend.app.models import DocumentVersion


@pytest.fixture
def client(test_settings) -> Iterator[TestClient]:
    app = create_app(test_settings)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        Base.metadata.create_all(app.state.database_engine)
        app.dependency_overrides[get_current_identity] = lambda: AuthenticatedIdentity(
            subject="auth0|object-owner",
            email="owner@example.com",
            display_name="Owner",
        )
        yield test_client


def test_download_is_backend_streamed_and_never_accepts_an_object_key(
    client: TestClient,
) -> None:
    identity = client.get("/api/v1/users/me").json()
    workspace_id = identity["workspaces"][0]["id"]
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": ("private.txt", b"private object", "text/plain")},
    )
    assert created.status_code == 201
    payload = created.json()
    document_id = payload["id"]
    version_id = payload["latest_version"]["id"]

    response = client.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/versions/"
        f"{version_id}/content",
        params={"object_key": "workspaces/another/private"},
    )
    assert response.status_code == 200
    assert response.content == b"private object"
    assert response.headers["content-length"] == str(len(response.content))
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "object_key" not in response.headers


def test_tampered_database_object_reference_fails_without_disclosure(
    client: TestClient,
) -> None:
    identity = client.get("/api/v1/users/me").json()
    workspace_id = identity["workspaces"][0]["id"]
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": ("private.txt", b"private object", "text/plain")},
    ).json()
    document_id = created["id"]
    version_id = created["latest_version"]["id"]
    app = cast(FastAPI, client.app)
    with app.state.session_factory.begin() as session:
        version = session.get(DocumentVersion, UUID(version_id))
        assert version is not None
        version.object_key = "workspaces/another/private"

    response = client.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/versions/"
        f"{version_id}/content"
    )
    assert response.status_code == 500
    assert response.json() == {
        "detail": "The document operation could not be completed"
    }
    assert "workspaces/another" not in response.text
