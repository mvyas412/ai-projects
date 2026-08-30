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
from backend.app.models import (
    Collection,
    CollectionDocument,
    Document,
    DocumentVersion,
    User,
    WorkspaceMembership,
    WorkspaceRole,
)


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
        yield test_client


def _workspace_id(client: TestClient) -> str:
    response = client.get("/api/v1/users/me")
    assert response.status_code == 200
    return response.json()["workspaces"][0]["id"]


def _upload(client: TestClient, workspace_id: str, content: bytes = b"%PDF-1.7 report"):
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        data={"title": "Quarterly report"},
        files={"file": ("report.pdf", content, "application/pdf")},
    )


def test_document_upload_list_version_and_archive(client: TestClient) -> None:
    workspace_id = _workspace_id(client)

    created = _upload(client, workspace_id)
    assert created.status_code == 201
    body = created.json()
    assert body["title"] == "Quarterly report"
    assert body["latest_version"]["version_number"] == 1
    assert body["latest_version"]["status"] == "uploaded"
    assert body["latest_version"]["byte_size"] > 0
    document_id = body["id"]

    listed = client.get(f"/api/v1/workspaces/{workspace_id}/documents")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [document_id]

    second = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/versions",
        files={"file": ("report-v2.pdf", b"%PDF-1.7 revised", "application/pdf")},
    )
    assert second.status_code == 201
    assert second.json()["version_number"] == 2

    duplicate = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/versions",
        files={"file": ("report-v2.pdf", b"%PDF-1.7 revised", "application/pdf")},
    )
    assert duplicate.status_code == 409

    detail = client.get(f"/api/v1/workspaces/{workspace_id}/documents/{document_id}")
    assert detail.status_code == 200
    assert [version["version_number"] for version in detail.json()["versions"]] == [2, 1]

    archived = client.delete(f"/api/v1/workspaces/{workspace_id}/documents/{document_id}")
    assert archived.status_code == 204
    assert client.get(f"/api/v1/workspaces/{workspace_id}/documents").json() == []
    assert (
        client.get(f"/api/v1/workspaces/{workspace_id}/documents/{document_id}").status_code
        == 404
    )


def test_collections_are_idempotent_and_workspace_scoped(client: TestClient) -> None:
    workspace_id = _workspace_id(client)
    document_id = _upload(client, workspace_id).json()["id"]

    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/collections",
        json={"name": "  Board   materials ", "description": "Current reports"},
    )
    assert created.status_code == 201
    assert created.json()["name"] == "Board materials"
    collection_id = created.json()["id"]

    duplicate = client.post(
        f"/api/v1/workspaces/{workspace_id}/collections",
        json={"name": "Board materials"},
    )
    assert duplicate.status_code == 409

    first_add = client.put(
        f"/api/v1/workspaces/{workspace_id}/collections/{collection_id}/documents/{document_id}"
    )
    second_add = client.put(
        f"/api/v1/workspaces/{workspace_id}/collections/{collection_id}/documents/{document_id}"
    )
    assert first_add.status_code == 204
    assert second_add.status_code == 204

    detail = client.get(f"/api/v1/workspaces/{workspace_id}/collections/{collection_id}")
    assert detail.status_code == 200
    assert detail.json()["document_count"] == 1
    assert [item["id"] for item in detail.json()["documents"]] == [document_id]

    removed = client.delete(
        f"/api/v1/workspaces/{workspace_id}/collections/{collection_id}/documents/{document_id}"
    )
    assert removed.status_code == 204
    assert client.get(
        f"/api/v1/workspaces/{workspace_id}/collections/{collection_id}"
    ).json()["document_count"] == 0


def test_non_member_cannot_discover_or_modify_documents(client: TestClient) -> None:
    workspace_id = _workspace_id(client)
    document_id = _upload(client, workspace_id).json()["id"]

    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_current_identity] = lambda: AuthenticatedIdentity(
        subject="auth0|bob",
        email="bob@example.com",
        display_name="Bob",
    )

    assert client.get(f"/api/v1/workspaces/{workspace_id}/documents").status_code == 404
    assert (
        client.get(f"/api/v1/workspaces/{workspace_id}/documents/{document_id}").status_code
        == 404
    )
    assert _upload(client, workspace_id).status_code == 404


def test_viewer_can_read_but_cannot_change_document_library(client: TestClient) -> None:
    workspace_id = _workspace_id(client)
    document_id = _upload(client, workspace_id).json()["id"]
    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_current_identity] = lambda: AuthenticatedIdentity(
        subject="auth0|viewer",
        email="viewer@example.com",
        display_name="Viewer",
    )
    assert client.get("/api/v1/users/me").status_code == 200
    with app.state.session_factory.begin() as session:
        viewer = session.scalar(select(User).where(User.external_subject == "auth0|viewer"))
        assert viewer is not None
        session.add(
            WorkspaceMembership(
                workspace_id=UUID(workspace_id),
                user_id=viewer.id,
                role=WorkspaceRole.VIEWER.value,
            )
        )

    assert client.get(f"/api/v1/workspaces/{workspace_id}/documents").status_code == 200
    assert (
        client.get(f"/api/v1/workspaces/{workspace_id}/documents/{document_id}").status_code
        == 200
    )
    assert _upload(client, workspace_id).status_code == 403
    assert client.delete(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}"
    ).status_code == 403


def test_upload_validation_and_storage_metadata(client: TestClient) -> None:
    workspace_id = _workspace_id(client)
    unsupported = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": ("payload.exe", b"binary", "application/octet-stream")},
    )
    empty = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert unsupported.status_code == 422
    assert empty.status_code == 422

    created = _upload(client, workspace_id)
    assert created.status_code == 201
    app = cast(FastAPI, client.app)
    with app.state.session_factory() as session:
        assert len(session.scalars(select(Document)).all()) == 1
        versions = session.scalars(select(DocumentVersion)).all()
        assert len(versions) == 1
        assert versions[0].object_key.startswith(f"workspaces/{workspace_id}/documents/")
        assert app.state.object_storage.exists(versions[0].object_key)
        assert session.scalars(select(Collection)).all() == []
        assert session.scalars(select(CollectionDocument)).all() == []
