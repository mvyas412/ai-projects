from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from backend.app.core.config import get_settings
from backend.app.db.rls import DatabasePurpose, set_rls_context
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.models import (
    AnswerFeedback,
    Conversation,
    ConversationMessage,
    MessageRole,
    ResourceVisibility,
    User,
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
)


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("MM_RAG_RUN_INTEGRATION_TESTS") != "1",
    reason="Set MM_RAG_RUN_INTEGRATION_TESTS=1 with PostgreSQL running",
)
def test_feedback_rls_limits_rows_to_submitter_or_workspace_admin() -> None:
    engine = create_database_engine(get_settings())
    factory = create_session_factory(engine)
    owner_id, member_id, outsider_id = uuid4(), uuid4(), uuid4()
    workspace_id, outsider_workspace_id = uuid4(), uuid4()
    conversation_id, message_id, feedback_id = uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC)
    try:
        with factory.begin() as session:
            session.add_all(
                [
                    User(id=owner_id, external_subject=f"test|feedback-owner-{owner_id}"),
                    User(id=member_id, external_subject=f"test|feedback-member-{member_id}"),
                    User(id=outsider_id, external_subject=f"test|feedback-outside-{outsider_id}"),
                ]
            )
            session.flush()
            session.add_all(
                [
                    Workspace(id=workspace_id, name="Feedback RLS", created_by_user_id=owner_id),
                    Workspace(
                        id=outsider_workspace_id,
                        name="Other feedback RLS",
                        created_by_user_id=outsider_id,
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    WorkspaceMembership(
                        workspace_id=workspace_id,
                        user_id=owner_id,
                        role=WorkspaceRole.OWNER.value,
                    ),
                    WorkspaceMembership(
                        workspace_id=workspace_id,
                        user_id=member_id,
                        role=WorkspaceRole.MEMBER.value,
                    ),
                    WorkspaceMembership(
                        workspace_id=outsider_workspace_id,
                        user_id=outsider_id,
                        role=WorkspaceRole.OWNER.value,
                    ),
                ]
            )
            session.flush()
            session.add(
                Conversation(
                    id=conversation_id,
                    workspace_id=workspace_id,
                    created_by_user_id=owner_id,
                    title="Feedback RLS conversation",
                    target_type="workspace",
                    visibility=ResourceVisibility.WORKSPACE.value,
                )
            )
            session.flush()
            session.add(
                ConversationMessage(
                    id=message_id,
                    conversation_id=conversation_id,
                    workspace_id=workspace_id,
                    sequence_number=1,
                    role=MessageRole.ASSISTANT.value,
                    content="not copied to telemetry",
                    citations=[],
                )
            )
            session.flush()
            session.add(
                AnswerFeedback(
                    id=feedback_id,
                    workspace_id=workspace_id,
                    conversation_id=conversation_id,
                    assistant_message_id=message_id,
                    submitter_user_id=member_id,
                    rating=-1,
                    reason="incomplete",
                    comment=None,
                    comment_consent=False,
                    snapshot_consent=False,
                    diagnostic_snapshot=None,
                    consent_policy_revision="phase7-feedback-consent-v1",
                    review_status="pending",
                    retention_expires_at=now + timedelta(days=90),
                )
            )

        for principal_id, selected_workspace, expected in (
            (owner_id, workspace_id, [feedback_id]),
            (member_id, workspace_id, [feedback_id]),
            (outsider_id, outsider_workspace_id, []),
        ):
            with factory.begin() as session:
                set_rls_context(
                    session,
                    purpose=DatabasePurpose.API,
                    workspace_id=selected_workspace,
                    principal_id=principal_id,
                )
                assert list(session.scalars(select(AnswerFeedback.id))) == expected
    finally:
        with factory.begin() as session:
            session.execute(delete(AnswerFeedback).where(AnswerFeedback.id == feedback_id))
            session.execute(
                delete(ConversationMessage).where(ConversationMessage.id == message_id)
            )
            session.execute(delete(Conversation).where(Conversation.id == conversation_id))
            session.execute(
                delete(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id.in_([workspace_id, outsider_workspace_id])
                )
            )
            session.execute(
                delete(Workspace).where(Workspace.id.in_([workspace_id, outsider_workspace_id]))
            )
            session.execute(delete(User).where(User.id.in_([owner_id, member_id, outsider_id])))
        engine.dispose()
