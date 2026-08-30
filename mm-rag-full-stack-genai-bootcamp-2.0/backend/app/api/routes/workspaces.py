from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user
from backend.app.db.session import get_db_session
from backend.app.models.user import User
from backend.app.models.workspace import Workspace, WorkspaceRole
from backend.app.schemas.identity import WorkspaceCreate, WorkspaceSummary
from backend.app.services.workspaces import WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _workspace_summary(workspace: Workspace, role: WorkspaceRole) -> WorkspaceSummary:
    return WorkspaceSummary(
        id=workspace.id,
        name=workspace.name,
        role=role,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


@router.get("", response_model=list[WorkspaceSummary], summary="List authorized workspaces")
def list_workspaces(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> list[WorkspaceSummary]:
    return [
        _workspace_summary(workspace, role)
        for workspace, role in WorkspaceService(session).list_for_user(user)
    ]


@router.post(
    "",
    response_model=WorkspaceSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Create a workspace",
)
def create_workspace(
    payload: WorkspaceCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> WorkspaceSummary:
    workspace, role = WorkspaceService(session).create(user=user, name=payload.name)
    return _workspace_summary(workspace, role)


@router.get("/{workspace_id}", response_model=WorkspaceSummary, summary="Get a workspace")
def get_workspace(
    workspace_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> WorkspaceSummary:
    result = WorkspaceService(session).get_for_user(user=user, workspace_id=workspace_id)
    if result is None:
        # Do not reveal whether a workspace exists to a non-member.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return _workspace_summary(*result)
