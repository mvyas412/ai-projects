from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AuditEventResponse(BaseModel):
    id: UUID
    action: str
    resource_type: str
    resource_id: UUID | None
    actor_user_id: UUID
    actor_display_name: str
    details: dict[str, Any]
    created_at: datetime
