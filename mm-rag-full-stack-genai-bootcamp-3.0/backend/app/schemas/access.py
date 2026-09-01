from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from backend.app.models.access import ResourceVisibility
from backend.app.services.policy import POLICY_REVISION, ResourceType


class ResourceVisibilityUpdate(BaseModel):
    visibility: ResourceVisibility


class ResourceACLGrantResponse(BaseModel):
    principal_user_id: UUID
    granted_by_user_id: UUID
    created_at: datetime


class ResourceAccessResponse(BaseModel):
    resource_type: ResourceType
    resource_id: UUID
    visibility: ResourceVisibility
    created_by_user_id: UUID
    grants: list[ResourceACLGrantResponse]
    policy_revision: str = POLICY_REVISION
