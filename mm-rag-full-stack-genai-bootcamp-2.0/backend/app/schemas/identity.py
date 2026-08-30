from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.models.workspace import WorkspaceRole


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str | None
    display_name: str | None
    created_at: datetime
    updated_at: datetime


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Workspace name cannot be blank")
        return normalized


class WorkspaceSummary(BaseModel):
    id: UUID
    name: str
    role: WorkspaceRole
    created_at: datetime
    updated_at: datetime


class CurrentUserResponse(BaseModel):
    user: UserProfile
    workspaces: list[WorkspaceSummary]
