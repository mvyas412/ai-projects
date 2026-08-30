from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LivenessResponse(BaseModel):
    status: Literal["healthy"] = "healthy"
    service: str
    version: str


class DependencyReadiness(BaseModel):
    status: Literal["ready", "unavailable"]
    latency_ms: float = Field(ge=0)


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    service: str
    version: str
    checks: dict[str, DependencyReadiness]
