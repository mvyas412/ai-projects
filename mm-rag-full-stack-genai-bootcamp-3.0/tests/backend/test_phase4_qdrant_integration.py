from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from qdrant_client import QdrantClient, models

from backend.app.core.config import get_settings
from backend.app.rag.engine import (
    RAGDocumentScope,
    RAGRequest,
    _authorized_citation,
    _retrieval_filter,
)


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("MM_RAG_RUN_INTEGRATION_TESTS") != "1",
    reason="Set MM_RAG_RUN_INTEGRATION_TESTS=1 with Compose services running",
)
def test_qdrant_query_and_result_validation_cannot_cross_workspace_scope() -> None:
    settings = get_settings()
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=(
            settings.qdrant_api_key.get_secret_value()
            if settings.qdrant_api_key is not None
            else None
        ),
        check_compatibility=False,
    )
    collection = f"phase4_scope_{uuid4().hex}"
    first_workspace, second_workspace = uuid4(), uuid4()
    first_document, second_document = uuid4(), uuid4()
    first_version, second_version = uuid4(), uuid4()
    first_generation, second_generation = uuid4(), uuid4()
    try:
        client.create_collection(
            collection_name=collection,
            vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE),
        )
        client.upsert(
            collection_name=collection,
            wait=True,
            points=[
                models.PointStruct(
                    id=str(uuid4()),
                    vector=[1.0, 0.0],
                    payload={
                        "tenant_id": str(first_workspace),
                        "workspace_id": str(first_workspace),
                        "document_id": str(first_document),
                        "document_version_id": str(first_version),
                        "generation_id": str(first_generation),
                        "content": "first workspace",
                    },
                ),
                models.PointStruct(
                    id=str(uuid4()),
                    vector=[1.0, 0.0],
                    payload={
                        "tenant_id": str(second_workspace),
                        "workspace_id": str(second_workspace),
                        "document_id": str(second_document),
                        "document_version_id": str(second_version),
                        "generation_id": str(second_generation),
                        "content": "second workspace",
                    },
                ),
            ],
        )
        request = RAGRequest(
            workspace_id=first_workspace,
            documents=(
                RAGDocumentScope(first_document, first_version, first_generation),
            ),
            query="scope",
            history=(),
        )
        points = client.query_points(
            collection_name=collection,
            query=[1.0, 0.0],
            query_filter=_retrieval_filter(request),
            limit=10,
            with_payload=True,
        ).points
        assert len(points) == 1
        citation = _authorized_citation(
            SimpleNamespace(payload=points[0].payload, score=points[0].score), request
        )
        assert citation.document_id == first_document
    finally:
        if client.collection_exists(collection):
            client.delete_collection(collection)
        client.close()
