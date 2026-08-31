from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.models.user import User
from backend.app.models.workspace import Workspace, WorkspaceRole
from backend.app.repositories.workspaces import WorkspaceRepository
from backend.app.services.audit import record_audit_event


class WorkspaceService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._workspaces = WorkspaceRepository(session)

    def list_for_user(self, user: User) -> list[tuple[Workspace, WorkspaceRole]]:
        return self._workspaces.list_for_user(user.id)

    def create(self, *, user: User, name: str) -> tuple[Workspace, WorkspaceRole]:
        workspace = Workspace(name=name, created_by_user_id=user.id)
        with self._session.begin():
            self._workspaces.add(workspace, user_id=user.id, role=WorkspaceRole.OWNER)
            record_audit_event(
                self._session,
                workspace_id=workspace.id,
                actor_user_id=user.id,
                action="workspace.created",
                resource_type="workspace",
                resource_id=workspace.id,
            )
        return workspace, WorkspaceRole.OWNER

    def get_for_user(
        self,
        *,
        user: User,
        workspace_id: UUID,
    ) -> tuple[Workspace, WorkspaceRole] | None:
        return self._workspaces.get_for_user(workspace_id, user.id)
