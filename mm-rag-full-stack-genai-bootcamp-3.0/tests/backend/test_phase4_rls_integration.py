from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError

from backend.app.core.config import get_settings
from backend.app.db.rls import DatabasePurpose, set_rls_context
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.models import Document, User, Workspace, WorkspaceMembership, WorkspaceRole


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("MM_RAG_RUN_INTEGRATION_TESTS") != "1",
    reason="Set MM_RAG_RUN_INTEGRATION_TESTS=1 with Compose services running",
)
def test_postgres_rls_isolates_unscoped_queries_and_runtime_roles() -> None:
    engine = create_database_engine(get_settings())
    factory = create_session_factory(engine)
    first_user_id, second_user_id = uuid4(), uuid4()
    first_workspace_id, second_workspace_id = uuid4(), uuid4()
    first_document_id, second_document_id = uuid4(), uuid4()

    try:
        with factory.begin() as session:
            session.add_all(
                [
                    User(id=first_user_id, external_subject=f"test|rls-{first_user_id}"),
                    User(id=second_user_id, external_subject=f"test|rls-{second_user_id}"),
                ]
            )
            session.flush()
            session.add_all(
                [
                    Workspace(
                        id=first_workspace_id,
                        name="RLS first",
                        created_by_user_id=first_user_id,
                    ),
                    Workspace(
                        id=second_workspace_id,
                        name="RLS second",
                        created_by_user_id=second_user_id,
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    WorkspaceMembership(
                        workspace_id=first_workspace_id,
                        user_id=first_user_id,
                        role=WorkspaceRole.MEMBER.value,
                    ),
                    WorkspaceMembership(
                        workspace_id=second_workspace_id,
                        user_id=second_user_id,
                        role=WorkspaceRole.MEMBER.value,
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    Document(
                        id=first_document_id,
                        workspace_id=first_workspace_id,
                        created_by_user_id=first_user_id,
                        title="First",
                        original_filename="first.txt",
                        media_type="text/plain",
                    ),
                    Document(
                        id=second_document_id,
                        workspace_id=second_workspace_id,
                        created_by_user_id=second_user_id,
                        title="Second",
                        original_filename="second.txt",
                        media_type="text/plain",
                    ),
                ]
            )

        with factory.begin() as session:
            set_rls_context(
                session,
                purpose=DatabasePurpose.API,
                workspace_id=first_workspace_id,
                principal_id=first_user_id,
            )
            assert list(session.scalars(select(Document.id))) == [first_document_id]

        with factory.begin() as session:
            set_rls_context(
                session,
                purpose=DatabasePurpose.API,
                workspace_id=second_workspace_id,
                principal_id=second_user_id,
            )
            assert list(session.scalars(select(Document.id))) == [second_document_id]

        with pytest.raises(DBAPIError):
            with factory.begin() as session:
                set_rls_context(
                    session,
                    purpose=DatabasePurpose.API,
                    workspace_id=first_workspace_id,
                    principal_id=first_user_id,
                )
                session.execute(text("ALTER TABLE documents DISABLE ROW LEVEL SECURITY"))

        with pytest.raises(DBAPIError):
            with factory.begin() as session:
                set_rls_context(session, purpose=DatabasePurpose.DISPATCHER)
                session.scalar(select(Document.id).limit(1))
    finally:
        with factory.begin() as session:
            session.execute(
                delete(Document).where(
                    Document.id.in_([first_document_id, second_document_id])
                )
            )
            session.execute(
                delete(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id.in_(
                        [first_workspace_id, second_workspace_id]
                    )
                )
            )
            session.execute(
                delete(Workspace).where(
                    Workspace.id.in_([first_workspace_id, second_workspace_id])
                )
            )
            session.execute(
                delete(User).where(User.id.in_([first_user_id, second_user_id]))
            )
        engine.dispose()
