from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.app.models.audit import AuditActorKind, AuditResult


class AuditEventResponse(BaseModel):
    id: UUID
    action: str
    resource_type: str
    resource_id: UUID | None
    actor_kind: AuditActorKind
    actor_user_id: UUID | None
    service_actor: str | None
    actor_display_name: str
    result: AuditResult
    details: dict[str, Any]
    created_at: datetime


class SecurityAuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    actor_kind: AuditActorKind
    actor_user_id: UUID | None
    service_actor: str | None
    action: str
    resource_type: str
    resource_id: UUID | None
    result: AuditResult
    policy_revision: str
    correlation_id: str
    schema_version: int
    details: dict[str, Any]
    created_at: datetime


class ComplianceExportCreate(BaseModel):
    range_start: datetime
    range_end: datetime


class ComplianceExportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    requested_by_user_id: UUID
    range_start: datetime
    range_end: datetime
    status: str
    schema_version: int
    event_count: int
    content_sha256: str
    byte_size: int
    completed_at: datetime
    created_at: datetime
