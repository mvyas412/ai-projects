from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user
from backend.app.db.session import get_db_session
from backend.app.models.user import User
from backend.app.schemas.access import (
    ResourceAccessResponse,
    ResourceACLGrantResponse,
    ResourceVisibilityUpdate,
)
from backend.app.services.access import (
    AccessControlError,
    AccessControlService,
    AccessPermissionDeniedError,
    AccessPrincipalNotFoundError,
    AccessResourceNotFoundError,
)
from backend.app.services.policy import ResourceContext, ResourceType

router = APIRouter(prefix="/workspaces/{workspace_id}/access", tags=["access-policy"])


def _translate(exc: AccessControlError) -> HTTPException:
    if isinstance(exc, (AccessResourceNotFoundError, AccessPrincipalNotFoundError)):
        return HTTPException(status_code=404, detail="Resource not found")
    if isinstance(exc, AccessPermissionDeniedError):
        return HTTPException(status_code=403, detail="Insufficient access")
    return HTTPException(status_code=500, detail="The access-policy operation failed")


def _response(context: ResourceContext, grants) -> ResourceAccessResponse:
    return ResourceAccessResponse(
        resource_type=context.resource_type,
        resource_id=context.resource_id,
        visibility=context.visibility,
        created_by_user_id=context.created_by_user_id,
        grants=[
            ResourceACLGrantResponse(
                principal_user_id=grant.principal_user_id,
                granted_by_user_id=grant.granted_by_user_id,
                created_at=grant.created_at,
            )
            for grant in grants
        ],
    )


@router.get("/{resource_type}/{resource_id}", response_model=ResourceAccessResponse)
def get_resource_access(
    workspace_id: UUID,
    resource_type: ResourceType,
    resource_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ResourceAccessResponse:
    try:
        return _response(
            *AccessControlService(session).get_access(
                user=user,
                workspace_id=workspace_id,
                resource_type=resource_type,
                resource_id=resource_id,
            )
        )
    except AccessControlError as exc:
        raise _translate(exc) from exc


@router.put("/{resource_type}/{resource_id}/visibility", response_model=ResourceAccessResponse)
def update_resource_visibility(
    workspace_id: UUID,
    resource_type: ResourceType,
    resource_id: UUID,
    payload: ResourceVisibilityUpdate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ResourceAccessResponse:
    try:
        return _response(
            *AccessControlService(session).set_visibility(
                user=user,
                workspace_id=workspace_id,
                resource_type=resource_type,
                resource_id=resource_id,
                visibility=payload.visibility,
            )
        )
    except AccessControlError as exc:
        raise _translate(exc) from exc


@router.put(
    "/{resource_type}/{resource_id}/grants/{principal_user_id}",
    response_model=ResourceAccessResponse,
    status_code=status.HTTP_200_OK,
)
def grant_resource_access(
    workspace_id: UUID,
    resource_type: ResourceType,
    resource_id: UUID,
    principal_user_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ResourceAccessResponse:
    try:
        return _response(
            *AccessControlService(session).grant(
                user=user,
                workspace_id=workspace_id,
                resource_type=resource_type,
                resource_id=resource_id,
                principal_user_id=principal_user_id,
            )
        )
    except AccessControlError as exc:
        raise _translate(exc) from exc


@router.delete(
    "/{resource_type}/{resource_id}/grants/{principal_user_id}",
    response_model=ResourceAccessResponse,
)
def revoke_resource_access(
    workspace_id: UUID,
    resource_type: ResourceType,
    resource_id: UUID,
    principal_user_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ResourceAccessResponse:
    try:
        return _response(
            *AccessControlService(session).revoke(
                user=user,
                workspace_id=workspace_id,
                resource_type=resource_type,
                resource_id=resource_id,
                principal_user_id=principal_user_id,
            )
        )
    except AccessControlError as exc:
        raise _translate(exc) from exc
