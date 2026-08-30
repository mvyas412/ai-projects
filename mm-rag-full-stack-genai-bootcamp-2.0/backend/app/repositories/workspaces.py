from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.workspace import Workspace, WorkspaceMembership, WorkspaceRole


class WorkspaceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, workspace: Workspace, *, user_id: UUID, role: WorkspaceRole) -> None:
        self._session.add(workspace)
        self._session.flush()
        self._session.add(
            WorkspaceMembership(workspace_id=workspace.id, user_id=user_id, role=role.value)
        )

    def list_for_user(self, user_id: UUID) -> list[tuple[Workspace, WorkspaceRole]]:
        statement = (
            select(Workspace, WorkspaceMembership.role)
            .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
            .where(WorkspaceMembership.user_id == user_id)
            .order_by(Workspace.created_at, Workspace.id)
        )
        return [
            (workspace, WorkspaceRole(role))
            for workspace, role in self._session.execute(statement).all()
        ]

    def get_for_user(
        self,
        workspace_id: UUID,
        user_id: UUID,
    ) -> tuple[Workspace, WorkspaceRole] | None:
        statement = (
            select(Workspace, WorkspaceMembership.role)
            .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
            .where(
                Workspace.id == workspace_id,
                WorkspaceMembership.user_id == user_id,
            )
        )
        row = self._session.execute(statement).one_or_none()
        return (row[0], WorkspaceRole(row[1])) if row is not None else None
