from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.lifecycle import LifecyclePlanState, LifecycleResourceType


class LifecyclePlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    resource_type: LifecycleResourceType
    resource_id: UUID
    state: LifecyclePlanState
    policy_revision: str
    execute_after: datetime
    created_at: datetime
    completed_at: datetime | None


class RetentionPreviewResponse(BaseModel):
    policy_revision: str
    generated_at: datetime
    preview_token: str
    due_document_deletions: int
    due_conversation_deletions: int
    inactive_generations: int
    terminal_jobs: int
    security_audit_events: int
    orphan_objects: int


class RetentionApplyRequest(BaseModel):
    preview_token: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class RetentionApplyResponse(BaseModel):
    policy_revision: str
    completed_plans: int
    blocked_plans: int
    deleted_inactive_generations: int
    deleted_terminal_jobs: int
    deleted_security_audit_events: int
    deleted_orphan_objects: int


class RetentionHoldRequest(BaseModel):
    reason_code: str = Field(
        min_length=2,
        max_length=80,
        pattern=r"^[a-z][a-z0-9_.-]+$",
    )


class RetentionHoldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    resource_type: LifecycleResourceType
    resource_id: UUID
    reason_code: str
    created_at: datetime


class OrphanInventoryResponse(BaseModel):
    observed_objects: int
    orphan_objects: int
    new_evidence: int
    cleared_evidence: int
