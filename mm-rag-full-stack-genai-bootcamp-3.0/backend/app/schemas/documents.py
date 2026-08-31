from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.models.access import ResourceVisibility
from backend.app.models.document import DocumentVersionStatus


class DocumentVersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    version_number: int
    content_sha256: str
    ingestion_fingerprint: str
    byte_size: int
    status: DocumentVersionStatus
    failure_reason: str | None
    active_generation_id: UUID | None = None
    active_generation_promoted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DocumentSummary(BaseModel):
    id: UUID
    workspace_id: UUID
    title: str
    original_filename: str
    media_type: str
    visibility: ResourceVisibility
    archived_at: datetime | None
    latest_version: DocumentVersionSummary
    created_at: datetime
    updated_at: datetime


class DocumentDetail(DocumentSummary):
    versions: list[DocumentVersionSummary]


class DocumentIndexingResponse(BaseModel):
    version: DocumentVersionSummary
    chunk_count: int


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Collection name cannot be blank")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class CollectionSummary(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    visibility: ResourceVisibility
    document_count: int
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CollectionDetail(CollectionSummary):
    documents: list[DocumentSummary]
