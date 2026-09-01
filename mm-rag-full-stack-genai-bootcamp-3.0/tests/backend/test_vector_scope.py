from types import SimpleNamespace
from uuid import uuid4

import pytest
from qdrant_client import models

from backend.app.rag.engine import (
    RAGDocumentScope,
    RAGRequest,
    RAGUnavailableError,
    _authorized_citation,
    _retrieval_filter,
)
from backend.app.retrieval.scope import (
    INDEXED_SCOPE_PAYLOAD_FIELDS,
    SCOPE_PAYLOAD_FIELDS,
    VectorScope,
    ensure_scope_payload_indexes,
    workspace_filter,
)


class FakeIndexClient:
    def __init__(self, *, exists: bool) -> None:
        self.exists = exists
        self.calls: list[tuple[str, str, models.PayloadSchemaType, bool]] = []

    def collection_exists(self, collection_name: str) -> bool:
        return self.exists

    def create_payload_index(
        self,
        collection_name: str,
        field_name: str,
        field_schema: models.PayloadSchemaType,
        *,
        wait: bool,
    ) -> object:
        self.calls.append((collection_name, field_name, field_schema, wait))
        return object()


def _conditions(qdrant_filter):
    return {condition.key: condition.match.value for condition in qdrant_filter.must}


def test_vector_scope_payload_and_filter_include_every_tenant_dimension() -> None:
    workspace_id = uuid4()
    scope = VectorScope(
        workspace_id=workspace_id,
        document_id=uuid4(),
        document_version_id=uuid4(),
    )

    payload = scope.payload()
    assert tuple(payload) == SCOPE_PAYLOAD_FIELDS
    assert payload["tenant_id"] == str(workspace_id)
    assert payload["workspace_id"] == str(workspace_id)
    assert _conditions(scope.filter()) == payload


def test_workspace_filter_never_relies_on_caller_supplied_document_scope() -> None:
    workspace_id = uuid4()

    assert _conditions(workspace_filter(workspace_id)) == {
        "tenant_id": str(workspace_id),
        "workspace_id": str(workspace_id),
    }


def test_scope_payload_indexes_are_created_for_existing_collection() -> None:
    client = FakeIndexClient(exists=True)

    assert ensure_scope_payload_indexes(client, "documents") is True
    assert [call[1] for call in client.calls] == list(INDEXED_SCOPE_PAYLOAD_FIELDS)
    assert all(call[2] == models.PayloadSchemaType.KEYWORD for call in client.calls)
    assert all(call[3] is True for call in client.calls)


def test_scope_payload_indexes_wait_until_collection_exists() -> None:
    client = FakeIndexClient(exists=False)

    assert ensure_scope_payload_indexes(client, "documents") is False
    assert client.calls == []


def test_retrieval_filter_requires_bounded_active_generation_scope() -> None:
    request = RAGRequest(
        workspace_id=uuid4(),
        documents=(RAGDocumentScope(uuid4(), uuid4(), None),),
        query="question",
        history=(),
    )

    with pytest.raises(RAGUnavailableError, match="incomplete"):
        _retrieval_filter(request)


def test_returned_vector_must_match_every_authorized_scope_dimension() -> None:
    workspace_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    generation_id = uuid4()
    request = RAGRequest(
        workspace_id=workspace_id,
        documents=(RAGDocumentScope(document_id, version_id, generation_id),),
        query="question",
        history=(),
    )
    payload = {
        "tenant_id": str(workspace_id),
        "workspace_id": str(workspace_id),
        "document_id": str(document_id),
        "document_version_id": str(version_id),
        "generation_id": str(generation_id),
        "document_title": "Authorized",
        "content_type": "text/plain",
        "content": "Safe evidence",
    }

    citation = _authorized_citation(
        SimpleNamespace(payload=payload, score=0.9), request
    )
    assert citation.document_id == document_id

    payload["generation_id"] = str(uuid4())
    with pytest.raises(RAGUnavailableError, match="authorization"):
        _authorized_citation(SimpleNamespace(payload=payload, score=0.9), request)
