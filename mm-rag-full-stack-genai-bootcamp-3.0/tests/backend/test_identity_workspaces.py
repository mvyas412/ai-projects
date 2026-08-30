from collections.abc import Iterator
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.core.security import AuthenticatedIdentity, get_current_identity
from backend.app.db.base import Base
from backend.app.main import create_app
from backend.app.models import User, Workspace, WorkspaceMembership


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


def test_missing_bearer_token_is_rejected(test_settings) -> None:
    app = create_app(test_settings)
    with TestClient(app) as client:
        response = client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_first_request_provisions_user_and_owner_workspace_once(client: TestClient) -> None:
    first = client.get("/api/v1/users/me")
    second = client.get("/api/v1/users/me")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    body = first.json()
    assert body["user"]["email"] == "alice@example.com"
    assert body["workspaces"][0]["name"] == "Personal workspace"
    assert body["workspaces"][0]["role"] == "owner"


def test_workspace_create_list_and_member_only_lookup(client: TestClient) -> None:
    created = client.post("/api/v1/workspaces", json={"name": "  Research   team "})
    assert created.status_code == 201
    assert created.json()["name"] == "Research team"
    assert created.json()["role"] == "owner"

    listed = client.get("/api/v1/workspaces")
    assert listed.status_code == 200
    assert {item["name"] for item in listed.json()} == {"Personal workspace", "Research team"}

    workspace_id = created.json()["id"]
    found = client.get(f"/api/v1/workspaces/{workspace_id}")
    assert found.status_code == 200

    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_current_identity] = lambda: AuthenticatedIdentity(
        subject="auth0|bob",
        email="bob@example.com",
        display_name="Bob",
    )
    hidden = client.get(f"/api/v1/workspaces/{workspace_id}")
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "Workspace not found"}


def test_database_relationships_are_created(client: TestClient) -> None:
    client.get("/api/v1/users/me")
    factory = cast(FastAPI, client.app).state.session_factory
    with factory() as session:
        assert len(session.scalars(select(User)).all()) == 1
        assert len(session.scalars(select(Workspace)).all()) == 1
        assert len(session.scalars(select(WorkspaceMembership)).all()) == 1
