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
    AnswerFeedback,
    Conversation,
    ConversationMessage,
    MessageRole,
    ResourceVisibility,
    User,
    WorkspaceMembership,
    WorkspaceRole,
)


def _identity(subject: str = "auth0|alice", email: str = "alice@example.com"):
    return AuthenticatedIdentity(subject=subject, email=email, display_name=email.split("@")[0])


@pytest.fixture
def client(test_settings) -> Iterator[TestClient]:
    app = create_app(test_settings)
    with TestClient(app) as test_client:
        Base.metadata.create_all(app.state.database_engine)
        app.dependency_overrides[get_current_identity] = _identity
        yield test_client


def _answer(client: TestClient) -> tuple[str, str, str]:
    profile = client.get("/api/v1/users/me").json()
    workspace_id = profile["workspaces"][0]["id"]
    user_id = profile["user"]["id"]
    app = cast(FastAPI, client.app)
    with app.state.session_factory.begin() as session:
        conversation = Conversation(
            workspace_id=UUID(workspace_id),
            created_by_user_id=UUID(user_id),
            title="Feedback test",
            target_type="workspace",
            visibility=ResourceVisibility.WORKSPACE.value,
        )
        session.add(conversation)
        session.flush()
        message = ConversationMessage(
            conversation_id=conversation.id,
            workspace_id=UUID(workspace_id),
            sequence_number=1,
            role=MessageRole.ASSISTANT.value,
            content="Private answer content must not be copied into diagnostics.",
            citations=[
                {
                    "document_id": "00000000-0000-0000-0000-000000000001",
                    "document_version_id": "00000000-0000-0000-0000-000000000002",
                    "generation_id": "00000000-0000-0000-0000-000000000003",
                }
            ],
            model_name="test-model",
        )
        session.add(message)
        session.flush()
        return workspace_id, str(conversation.id), str(message.id)


def test_feedback_requires_consent_and_preserves_content_boundary(client: TestClient) -> None:
    workspace_id, conversation_id, message_id = _answer(client)
    endpoint = (
        f"/api/v1/workspaces/{workspace_id}/feedback/conversations/"
        f"{conversation_id}/messages/{message_id}"
    )
    rejected = client.post(
        endpoint,
        json={"rating": -1, "reason": "incorrect", "comment": "detail"},
    )
    assert rejected.status_code == 422

    accepted = client.post(
        endpoint,
        json={
            "rating": -1,
            "reason": "citation_issue",
            "comment": "The cited page looks unrelated.",
            "comment_consent": True,
            "snapshot_consent": True,
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["review_status"] == "pending"
    assert "diagnostic_snapshot" not in accepted.json()

    app = cast(FastAPI, client.app)
    with app.state.session_factory() as session:
        feedback = session.scalar(select(AnswerFeedback))
        assert feedback is not None
        snapshot = feedback.diagnostic_snapshot
        assert snapshot is not None
        assert "content" not in snapshot
        assert "question" not in snapshot
        assert snapshot["citation_count"] == 1


def test_owner_can_review_but_member_cannot(client: TestClient) -> None:
    workspace_id, conversation_id, message_id = _answer(client)
    created = client.post(
        f"/api/v1/workspaces/{workspace_id}/feedback/conversations/"
        f"{conversation_id}/messages/{message_id}",
        json={"rating": 1, "reason": "helpful"},
    ).json()

    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_current_identity] = lambda: _identity(
        "auth0|bob", "bob@example.com"
    )
    bob = client.get("/api/v1/users/me").json()
    with app.state.session_factory.begin() as session:
        session.add(
            WorkspaceMembership(
                workspace_id=UUID(workspace_id),
                user_id=UUID(bob["user"]["id"]),
                role=WorkspaceRole.MEMBER.value,
            )
        )
    assert client.get(f"/api/v1/workspaces/{workspace_id}/feedback").status_code == 403

    app.dependency_overrides[get_current_identity] = _identity
    reviewed = client.post(
        f"/api/v1/workspaces/{workspace_id}/feedback/{created['id']}/review",
        json={"status": "promoted", "promoted_case_id": "citation-regression-001"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["review_status"] == "promoted"
    assert reviewed.json()["promoted_case_id"] == "citation-regression-001"

    with app.state.session_factory() as session:
        user = session.scalar(select(User).where(User.external_subject == "auth0|alice"))
        assert user is not None
