import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from backend.app.core.config import get_settings
from backend.app.db.rls import DatabasePurpose, set_rls_context
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.models import ConnectorInstallation, User, Workspace, WorkspaceMembership


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("MM_RAG_RUN_INTEGRATION_TESTS") != "1",
    reason="Set MM_RAG_RUN_INTEGRATION_TESTS=1 with PostgreSQL running",
)
def test_phase9_enterprise_records_are_tenant_scoped() -> None:
    factory = create_session_factory(create_database_engine(get_settings()))
    first_user, second_user = uuid4(), uuid4()
    first_workspace, second_workspace = uuid4(), uuid4()
    first_connector, second_connector = uuid4(), uuid4()
    try:
        with factory.begin() as session:
            session.add_all(
                [
                    User(id=first_user, external_subject=f"test|p9-{first_user}"),
                    User(id=second_user, external_subject=f"test|p9-{second_user}"),
                ]
            )
            session.flush()
            session.add_all(
                [
                    Workspace(
                        id=first_workspace, name="First", created_by_user_id=first_user
                    ),
                    Workspace(
                        id=second_workspace, name="Second", created_by_user_id=second_user
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    WorkspaceMembership(
                        workspace_id=first_workspace, user_id=first_user, role="owner"
                    ),
                    WorkspaceMembership(
                        workspace_id=second_workspace, user_id=second_user, role="owner"
                    ),
                    ConnectorInstallation(
                        id=first_connector,
                        workspace_id=first_workspace,
                        kind="google_drive",
                        name="First Drive",
                        credential_reference="vault://opaque/first",
                    ),
                    ConnectorInstallation(
                        id=second_connector,
                        workspace_id=second_workspace,
                        kind="google_drive",
                        name="Second Drive",
                        credential_reference="vault://opaque/second",
                    ),
                ]
            )

        with factory.begin() as session:
            set_rls_context(
                session,
                purpose=DatabasePurpose.API,
                workspace_id=first_workspace,
                principal_id=first_user,
            )
            visible = tuple(session.scalars(select(ConnectorInstallation.id)))
            assert visible == (first_connector,)
    finally:
        with factory.begin() as session:
            session.execute(
                delete(ConnectorInstallation).where(
                    ConnectorInstallation.id.in_((first_connector, second_connector))
                )
            )
            session.execute(
                delete(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id.in_(
                        (first_workspace, second_workspace)
                    )
                )
            )
            session.execute(
                delete(Workspace).where(
                    Workspace.id.in_((first_workspace, second_workspace))
                )
            )
            session.execute(delete(User).where(User.id.in_((first_user, second_user))))
