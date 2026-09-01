from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from qdrant_client import models

SCOPE_PAYLOAD_FIELDS = (
    "tenant_id",
    "workspace_id",
    "document_id",
    "document_version_id",
)
INDEXED_SCOPE_PAYLOAD_FIELDS = (*SCOPE_PAYLOAD_FIELDS, "generation_id")


class PayloadIndexClient(Protocol):
    def collection_exists(self, collection_name: str) -> bool: ...

    def create_payload_index(
        self,
        collection_name: str,
        field_name: str,
        field_schema: models.PayloadSchemaType | models.KeywordIndexParams,
        *,
        wait: bool,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class VectorScope:
    workspace_id: UUID
    document_id: UUID
    document_version_id: UUID
    generation_id: UUID | None = None

    def payload(self) -> dict[str, str]:
        workspace = str(self.workspace_id)
        payload = {
            "tenant_id": workspace,
            "workspace_id": workspace,
            "document_id": str(self.document_id),
            "document_version_id": str(self.document_version_id),
        }
        if self.generation_id is not None:
            payload["generation_id"] = str(self.generation_id)
        return payload

    def filter(self) -> models.Filter:
        return models.Filter(
            must=[
                _match(field, value)
                for field, value in self.payload().items()
            ]
        )


def workspace_filter(workspace_id: UUID) -> models.Filter:
    value = str(workspace_id)
    return models.Filter(
        must=[
            _match("tenant_id", value),
            _match("workspace_id", value),
        ]
    )


def ensure_scope_payload_indexes(client: PayloadIndexClient, collection_name: str) -> bool:
    """Create mandatory keyword indexes once the document-vector collection exists."""
    if not client.collection_exists(collection_name):
        return False
    for field in INDEXED_SCOPE_PAYLOAD_FIELDS:
        client.create_payload_index(
            collection_name=collection_name,
            field_name=field,
            field_schema=(
                models.KeywordIndexParams(
                    type=models.KeywordIndexType.KEYWORD,
                    is_tenant=True,
                )
                if field == "tenant_id"
                else models.PayloadSchemaType.KEYWORD
            ),
            wait=True,
        )
    return True


def _match(field: str, value: str) -> models.FieldCondition:
    return models.FieldCondition(key=field, match=models.MatchValue(value=value))
