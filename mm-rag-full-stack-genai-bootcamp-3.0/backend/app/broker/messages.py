from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class IngestionEventMessage(BaseModel):
    """Minimal untrusted wake-up message defined by ADR 0009."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    event_type: Literal["ingestion.job.available"]
    schema_version: Literal[1]
    job_id: UUID
    occurred_at: datetime

    def broker_body(self) -> bytes:
        return self.model_dump_json().encode("utf-8")

    @classmethod
    def from_body(cls, body: bytes) -> "IngestionEventMessage":
        if not body or len(body) > 4096:
            raise ValueError("Broker message size is invalid")
        return cls.model_validate_json(body)
