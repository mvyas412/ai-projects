import hashlib
from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.core.security import AuthenticatedIdentity, get_current_identity
from backend.app.db.base import Base
from backend.app.main import create_app
from backend.app.models.document import DocumentVersion
from backend.app.models.ingestion import IngestionJob
from backend.app.models.outbox import IngestionOutboxEvent


def _alice() -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        subject="auth0|async-alice",
        email="alice@example.com",
        display_name="Alice",
    )


@pytest.fixture
def client(test_settings) -> Iterator[TestClient]:
    app = create_app(test_settings)
    with TestClient(app) as test_client:
        Base.metadata.create_all(app.state.database_engine)
        app.dependency_overrides[get_current_identity] = _alice
        yield test_client


def _workspace_id(client: TestClient) -> str:
    response = client.get("/api/v1/users/me")
    assert response.status_code == 200
    return response.json()["workspaces"][0]["id"]


def _upload(client: TestClient, workspace_id: str, *, key: str, content: bytes = b"safe"):
    return client.post(
        f"/api/v1/workspaces/{workspace_id}/ingestion/uploads",
        headers={"Idempotency-Key": key},
        data={"title": "Async report"},
        files={"file": ("report.txt", content, "text/plain")},
    )


def test_async_upload_is_durable_idempotent_and_status_scoped(client: TestClient) -> None:
    workspace_id = _workspace_id(client)
    created = _upload(client, workspace_id, key="upload-1")
    assert created.status_code == 202
    payload = created.json()
    assert payload["replayed"] is False
    assert payload["document"]["latest_version"]["status"] == "uploaded"
    assert payload["job"]["state"] == "pending"
    assert payload["job"]["attempt_count"] == 0
    assert "object_key" not in created.text
    job_id = payload["job"]["id"]

    replay = _upload(client, workspace_id, key="upload-1")
    assert replay.status_code == 202
    assert replay.json()["replayed"] is True
    assert replay.json()["job"]["id"] == job_id
    assert replay.json()["document"]["id"] == payload["document"]["id"]

    conflict = _upload(client, workspace_id, key="upload-1", content=b"changed")
    assert conflict.status_code == 409

    app = client.app
    assert isinstance(app, FastAPI)
    with app.state.session_factory() as session:
        assert len(list(session.scalars(select(IngestionJob)))) == 1
        assert len(list(session.scalars(select(IngestionOutboxEvent)))) == 1

    status = client.get(
        f"/api/v1/workspaces/{workspace_id}/ingestion/jobs/{job_id}"
    )
    assert status.status_code == 200
    assert status.json()["progress"]["attempt_number"] == 0

    app.dependency_overrides[get_current_identity] = lambda: AuthenticatedIdentity(
        subject="auth0|async-bob",
        email="bob@example.com",
        display_name="Bob",
    )
    assert client.get(
        f"/api/v1/workspaces/{workspace_id}/ingestion/jobs/{job_id}"
    ).status_code == 404


def test_cancel_and_successor_retry_preserve_terminal_history(client: TestClient) -> None:
    workspace_id = _workspace_id(client)
    submitted = _upload(client, workspace_id, key="upload-cancel").json()
    job_id = submitted["job"]["id"]
    document_id = submitted["document"]["id"]

    cancelled = client.post(
        f"/api/v1/workspaces/{workspace_id}/ingestion/jobs/{job_id}/cancel"
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"
    detail = client.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}"
    )
    assert detail.json()["latest_version"]["status"] == "uploaded"

    successor = client.post(
        f"/api/v1/workspaces/{workspace_id}/ingestion/jobs/{job_id}/retry",
        headers={"Idempotency-Key": "retry-cancelled-1"},
    )
    assert successor.status_code == 202
    assert successor.json()["state"] == "pending"
    assert successor.json()["predecessor_job_id"] == job_id
    assert successor.json()["id"] != job_id


def test_async_endpoints_require_stable_idempotency_keys(client: TestClient) -> None:
    workspace_id = _workspace_id(client)
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/ingestion/uploads",
        files={"file": ("report.txt", b"safe", "text/plain")},
    )
    assert response.status_code == 422


def test_bounded_upload_replay_and_retry_rejection_preserve_authorization(client) -> None:
    app = client.app
    app.state.settings.execution_retry_profile = "pilot-single-attempt-v1"
    workspace_id = _workspace_id(client)
    submitted = _upload(client, workspace_id, key="pilot-upload")
    assert submitted.status_code == 202
    payload = submitted.json()
    job_id = payload["job"]["id"]
    assert payload["job"]["max_attempts"] == 1
    replay = _upload(client, workspace_id, key="pilot-upload")
    assert replay.status_code == 202 and replay.json()["replayed"]
    assert replay.json()["job"]["id"] == job_id
    assert client.post(
        f"/api/v1/workspaces/{workspace_id}/ingestion/jobs/{job_id}/cancel"
    ).status_code == 200
    retry = client.post(
        f"/api/v1/workspaces/{workspace_id}/ingestion/jobs/{job_id}/retry",
        headers={"Idempotency-Key": "pilot-successor"},
    )
    assert retry.status_code == 409 and "bounded" in retry.json()["detail"]
    fresh_key = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents/{payload['document']['id']}"
        f"/versions/{payload['job']['document_version_id']}/ingestion-jobs",
        headers={"Idempotency-Key": "pilot-new-key"},
    )
    assert fresh_key.status_code == 409
    with app.state.session_factory() as session:
        jobs = list(session.scalars(select(IngestionJob)))
        assert len(jobs) == 1 and jobs[0].state == "cancelled"
        assert len(list(session.scalars(select(IngestionOutboxEvent)))) == 1
    app.dependency_overrides[get_current_identity] = lambda: AuthenticatedIdentity(
        subject="auth0|async-outsider", email="outsider@example.test", display_name="Outsider"
    )
    denied = client.post(
        f"/api/v1/workspaces/{workspace_id}/ingestion/jobs/{job_id}/retry",
        headers={"Idempotency-Key": "unauthorized-retry"},
    )
    assert denied.status_code == 404


def test_representative_large_upload_streams_to_immutable_storage(
    client: TestClient,
) -> None:
    workspace_id = _workspace_id(client)
    content = (b"phase-3-large-document\n" * 512 * 1024)[: 10 * 1024 * 1024]
    response = _upload(client, workspace_id, key="large-upload-1", content=content)
    assert response.status_code == 202
    version_payload = response.json()["document"]["latest_version"]
    assert version_payload["byte_size"] == len(content)
    assert version_payload["content_sha256"] == hashlib.sha256(content).hexdigest()

    app = client.app
    assert isinstance(app, FastAPI)
    with app.state.session_factory() as session:
        job = session.get(IngestionJob, UUID(response.json()["job"]["id"]))
        assert job is not None
        version = session.get(DocumentVersion, job.document_version_id)
        assert version is not None
        object_key = version.object_key
    stored = app.state.object_storage.head(object_key)
    assert stored.byte_size == len(content)
    assert stored.content_sha256 == version_payload["content_sha256"]
