from collections.abc import Iterator
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.core.security import AuthenticatedIdentity, get_current_identity
from backend.app.db.base import Base
from backend.app.main import create_app
from backend.app.rag.engine import RAGAnswer, RAGCitation, RAGRequest
from backend.app.rag.indexing import IndexingRequest, IndexingResult


class FakeIndexer:
    def index(self, request: IndexingRequest) -> IndexingResult:
        return IndexingResult(chunk_count=3)


class FakeRAGEngine:
    def answer(self, request: RAGRequest) -> RAGAnswer:
        scope = request.documents[0]
        return RAGAnswer(
            content="Revenue increased, according to the authorized report [1].",
            citations=(
                RAGCitation(
                    document_id=scope.document_id,
                    document_version_id=scope.document_version_id,
                    document_title="Quarterly report",
                    content_type="application/pdf",
                    excerpt="Revenue increased by 18 percent.",
                    page_number=2,
                    score=0.93,
                ),
            ),
            model_name="fake-production-model",
            prompt_tokens=40,
            completion_tokens=12,
        )


class UnsafeRAGEngine:
    def answer(self, request: RAGRequest) -> RAGAnswer:
        safe = request.documents[0]
        return RAGAnswer(
            content="Unsafe response",
            citations=(
                RAGCitation(
                    document_id=safe.document_id,
                    document_version_id=safe.document_version_id,
                    document_title="Safe",
                    content_type="text/plain",
                    excerpt="Safe",
                ),
                RAGCitation(
                    document_id=safe.document_id,
                    document_version_id=type(safe.document_version_id)(int=0),
                    document_title="Injected",
                    content_type="text/plain",
                    excerpt="Unauthorized",
                ),
            ),
        )


def _identity() -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        subject="auth0|alice",
        email="alice@example.com",
        display_name="Alice",
    )


@pytest.fixture
def client(test_settings) -> Iterator[TestClient]:
    app = create_app(test_settings)
    with TestClient(app) as test_client:
        Base.metadata.create_all(app.state.database_engine)
        app.dependency_overrides[get_current_identity] = _identity
        app.state.document_indexer = FakeIndexer()
        app.state.rag_engine = FakeRAGEngine()
        yield test_client


def _workspace_id(client: TestClient) -> str:
    response = client.get("/api/v1/users/me")
    assert response.status_code == 200
    return response.json()["workspaces"][0]["id"]


def _ready_document(client: TestClient, workspace_id: str) -> tuple[str, str]:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        data={"title": "Quarterly report"},
        files={"file": ("report.txt", b"Revenue increased by 18 percent.", "text/plain")},
    )
    assert response.status_code == 201
    document_id = response.json()["id"]
    version_id = response.json()["latest_version"]["id"]
    indexed = client.post(
        f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/versions/"
        f"{version_id}/index"
    )
    assert indexed.status_code == 200
    assert indexed.json()["version"]["status"] == "ready"
    return document_id, version_id


def test_conversation_persists_messages_and_authorized_citations(client: TestClient) -> None:
    workspace_id = _workspace_id(client)
    document_id, version_id = _ready_document(client, workspace_id)
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/conversations",
        json={
            "title": "Board questions",
            "target_type": "documents",
            "document_ids": [document_id],
        },
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]
    original_updated_at = created.json()["updated_at"]

    exchange = client.post(
        f"/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/messages",
        json={"content": "How did revenue change?"},
    )
    assert exchange.status_code == 200
    citation = exchange.json()["assistant_message"]["citations"][0]
    assert citation["document_id"] == document_id
    assert citation["document_version_id"] == version_id
    assert citation["page_number"] == 2

    detail = client.get(
        f"/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}"
    )
    assert detail.status_code == 200
    assert [message["role"] for message in detail.json()["messages"]] == [
        "user",
        "assistant",
    ]
    assert detail.json()["message_count"] == 2
    listed = client.get(f"/api/v1/workspaces/{workspace_id}/conversations")
    assert listed.status_code == 200
    assert listed.json()[0]["updated_at"] != original_updated_at
    activity = client.get(f"/api/v1/workspaces/{workspace_id}/activity")
    answer_event = next(
        event
        for event in activity.json()
        if event["action"] == "conversation.message_created"
    )
    assert (
        answer_event["details"]["assistant_message_id"]
        == exchange.json()["assistant_message"]["id"]
    )


def test_conversation_survives_application_restart(test_settings) -> None:
    app = create_app(test_settings)
    with TestClient(app) as first:
        Base.metadata.create_all(app.state.database_engine)
        app.dependency_overrides[get_current_identity] = _identity
        app.state.document_indexer = FakeIndexer()
        app.state.rag_engine = FakeRAGEngine()
        workspace_id = _workspace_id(first)
        document_id, _ = _ready_document(first, workspace_id)
        created = first.post(
            f"/api/v1/workspaces/{workspace_id}/conversations",
            json={
                "title": "Persistent chat",
                "target_type": "documents",
                "document_ids": [document_id],
            },
        )
        conversation_id = created.json()["id"]
        assert first.post(
            f"/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/messages",
            json={"content": "Summarize the report"},
        ).status_code == 200

    restarted = create_app(test_settings)
    with TestClient(restarted) as second:
        restarted.dependency_overrides[get_current_identity] = _identity
        detail = second.get(
            f"/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}"
        )
        assert detail.status_code == 200
        assert detail.json()["message_count"] == 2


def test_conversations_hide_tenants_and_reject_unsafe_citations(client: TestClient) -> None:
    workspace_id = _workspace_id(client)
    document_id, _ = _ready_document(client, workspace_id)
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/conversations",
        json={
            "title": "Scoped chat",
            "target_type": "documents",
            "document_ids": [document_id],
        },
    )
    conversation_id = created.json()["id"]
    app = cast(FastAPI, client.app)
    app.state.rag_engine = UnsafeRAGEngine()
    unsafe = client.post(
        f"/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/messages",
        json={"content": "Leak another source"},
    )
    assert unsafe.status_code == 503
    assert client.get(
        f"/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}"
    ).json()["messages"] == []

    app.dependency_overrides[get_current_identity] = lambda: AuthenticatedIdentity(
        subject="auth0|bob", email="bob@example.com", display_name="Bob"
    )
    assert client.get(
        f"/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}"
    ).status_code == 404


def test_unconfigured_indexer_is_safe_and_retryable(test_settings) -> None:
    app = create_app(test_settings)
    with TestClient(app) as test_client:
        Base.metadata.create_all(app.state.database_engine)
        app.dependency_overrides[get_current_identity] = _identity
        workspace_id = _workspace_id(test_client)
        response = test_client.post(
            f"/api/v1/workspaces/{workspace_id}/documents",
            files={"file": ("notes.txt", b"Safe content", "text/plain")},
        )
        document_id = response.json()["id"]
        version_id = response.json()["latest_version"]["id"]
        indexed = test_client.post(
            f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/versions/"
            f"{version_id}/index"
        )
        assert indexed.status_code == 503
        detail = test_client.get(
            f"/api/v1/workspaces/{workspace_id}/documents/{document_id}"
        )
        assert detail.json()["latest_version"]["status"] == "uploaded"
