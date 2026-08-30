from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user
from backend.app.db.session import get_db_session
from backend.app.models.user import User
from backend.app.schemas.audit import AuditEventResponse
from backend.app.services.audit import AuditNotFoundError, AuditService

router = APIRouter(prefix="/workspaces/{workspace_id}/activity", tags=["activity"])


@router.get("", response_model=list[AuditEventResponse], summary="List workspace activity")
def list_activity(
    workspace_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[AuditEventResponse]:
    try:
        rows = AuditService(session).list_events(
            user=user, workspace_id=workspace_id, limit=limit
        )
    except AuditNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Resource not found") from exc
    return [
        AuditEventResponse(
            id=event.id,
            action=event.action,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            actor_display_name=actor.display_name or actor.email or "User",
            details=event.details,
            created_at=event.created_at,
        )
        for event, actor in rows
    ]
