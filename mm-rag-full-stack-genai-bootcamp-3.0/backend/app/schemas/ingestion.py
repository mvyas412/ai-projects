from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from backend.app.models.ingestion import IngestionJobState, IngestionProgressStage
from backend.app.schemas.documents import DocumentDetail


class IngestionProgress(BaseModel):
    stage: IngestionProgressStage | None
    attempt_number: int
    completed_units: int | None
    total_units: int | None
    unit: str | None
    percentage: int | None
    updated_at: datetime


class IngestionPublicError(BaseModel):
    code: str
    retryable: bool
    summary: str
    correlation_id: str


class IngestionJobSummary(BaseModel):
    id: UUID
    document_id: UUID
    document_version_id: UUID
    predecessor_job_id: UUID | None
    state: IngestionJobState
    revision: int
    attempt_count: int
    max_attempts: int
    cancel_requested: bool
    next_attempt_at: datetime | None
    progress: IngestionProgress
    error: IngestionPublicError | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class AsyncUploadResponse(BaseModel):
    document: DocumentDetail
    job: IngestionJobSummary
    replayed: bool
