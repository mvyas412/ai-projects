from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user
from backend.app.db.session import get_db_session
from backend.app.models.user import User
from backend.app.schemas.identity import CurrentUserResponse, UserProfile, WorkspaceSummary
from backend.app.services.workspaces import WorkspaceService

router = APIRouter(prefix="/users", tags=["identity"])


@router.get("/me", response_model=CurrentUserResponse, summary="Current user and workspaces")
def current_user(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> CurrentUserResponse:
    workspaces = WorkspaceService(session).list_for_user(user)
    return CurrentUserResponse(
        user=UserProfile.model_validate(user),
        workspaces=[
            WorkspaceSummary(
                id=workspace.id,
                name=workspace.name,
                role=role,
                created_at=workspace.created_at,
                updated_at=workspace.updated_at,
            )
            for workspace, role in workspaces
        ],
    )
