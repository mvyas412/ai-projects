from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.security import AuthenticatedIdentity
from backend.app.models.user import User
from backend.app.models.workspace import Workspace, WorkspaceRole
from backend.app.repositories.users import UserRepository
from backend.app.repositories.workspaces import WorkspaceRepository
from backend.app.services.audit import record_audit_event


class IdentityProvisioningService:
    """Map a trusted external subject to an internal user and personal workspace."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def provision(self, identity: AuthenticatedIdentity) -> User:
        try:
            with self._session.begin():
                user = self._provision_in_transaction(identity)
        except IntegrityError:
            # A concurrent first request may win the unique-subject insert.
            self._session.rollback()
            with self._session.begin():
                concurrent_user = UserRepository(self._session).get_by_external_subject(
                    identity.subject
                )
                if concurrent_user is None:
                    raise
                self._refresh_profile(concurrent_user, identity)
                user = concurrent_user
        return user

    def _provision_in_transaction(self, identity: AuthenticatedIdentity) -> User:
        users = UserRepository(self._session)
        user = users.get_by_external_subject(identity.subject)
        if user is not None:
            self._refresh_profile(user, identity)
            return user

        user = User(
            external_subject=identity.subject,
            email=identity.email,
            display_name=identity.display_name,
        )
        users.add(user)
        self._session.flush()
        workspace = Workspace(name="Personal workspace", created_by_user_id=user.id)
        WorkspaceRepository(self._session).add(
            workspace,
            user_id=user.id,
            role=WorkspaceRole.OWNER,
        )
        record_audit_event(
            self._session,
            workspace_id=workspace.id,
            actor_user_id=user.id,
            action="workspace.provisioned",
            resource_type="workspace",
            resource_id=workspace.id,
            details={"name": workspace.name},
        )
        return user

    @staticmethod
    def _refresh_profile(user: User, identity: AuthenticatedIdentity) -> None:
        if identity.email is not None:
            user.email = identity.email
        if identity.display_name is not None:
            user.display_name = identity.display_name
