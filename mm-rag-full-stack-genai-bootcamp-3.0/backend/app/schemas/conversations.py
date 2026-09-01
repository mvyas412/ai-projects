from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.models.access import ResourceVisibility
from backend.app.models.conversation import ConversationTargetType, MessageRole


class ConversationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    target_type: ConversationTargetType = ConversationTargetType.WORKSPACE
    collection_id: UUID | None = None
    document_ids: list[UUID] = Field(default_factory=list, max_length=50)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Conversation title cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_target(self):
        if self.target_type == ConversationTargetType.COLLECTION:
            if self.collection_id is None or self.document_ids:
                raise ValueError("Collection conversations require only collection_id")
        elif self.target_type == ConversationTargetType.DOCUMENTS:
            if self.collection_id is not None or not self.document_ids:
                raise ValueError("Document conversations require document_ids")
            if len(set(self.document_ids)) != len(self.document_ids):
                raise ValueError("document_ids must be unique")
        elif self.collection_id is not None or self.document_ids:
            raise ValueError("Workspace conversations cannot include narrower targets")
        return self


class Citation(BaseModel):
    document_id: UUID
    document_version_id: UUID
    document_title: str
    page_number: int | None = None
    content_type: str
    excerpt: str = Field(max_length=1000)
    score: float | None = None


class ConversationMessageResponse(BaseModel):
    id: UUID
    sequence_number: int
    role: MessageRole
    content: str
    citations: list[Citation]
    model_name: str | None
    created_at: datetime


class ConversationSummary(BaseModel):
    id: UUID
    workspace_id: UUID
    title: str
    target_type: ConversationTargetType
    collection_id: UUID | None
    document_ids: list[UUID]
    visibility: ResourceVisibility
    message_count: int
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[ConversationMessageResponse]


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=12_000)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Message cannot be blank")
        return normalized


class MessageExchangeResponse(BaseModel):
    user_message: ConversationMessageResponse
    assistant_message: ConversationMessageResponse
