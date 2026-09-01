from __future__ import annotations

import os
from uuid import uuid4

import pytest
from qdrant_client import QdrantClient, models

from backend.app.core.config import get_settings
from backend.app.rag.engine import (
    RAGDocumentScope,
    RAGRequest,
    _authorized_candidate,
    _retrieval_filter,
)
from backend.app.retrieval.ranking import reciprocal_rank_fusion
from backend.app.retrieval.sparse import SPARSE_VECTOR_NAME


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("MM_RAG_RUN_INTEGRATION_TESTS") != "1",
    reason="Set MM_RAG_RUN_INTEGRATION_TESTS=1 with Compose services running",
)
def test_real_qdrant_hybrid_legs_preserve_workspace_and_generation_scope() -> None:
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
    collection = f"phase5_hybrid_{uuid4().hex}"
    workspace, other_workspace = uuid4(), uuid4()
    document, other_document = uuid4(), uuid4()
    version, other_version = uuid4(), uuid4()
    generation, other_generation = uuid4(), uuid4()
    try:
        client.create_collection(
            collection_name=collection,
            vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE),
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: models.SparseVectorParams(modifier=models.Modifier.IDF)
            },
        )
        points = []
        for point_id, scope, dense, sparse, content in (
            (uuid4(), (workspace, document, version, generation), [1.0, 0.0], [1], "allowed"),
            (
                uuid4(),
                (other_workspace, other_document, other_version, other_generation),
                [1.0, 0.0],
                [1],
                "other tenant",
            ),
        ):
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector={
                        "": dense,
                        SPARSE_VECTOR_NAME: models.SparseVector(indices=sparse, values=[1.0]),
                    },
                    payload={
                        "tenant_id": str(scope[0]),
                        "workspace_id": str(scope[0]),
                        "document_id": str(scope[1]),
                        "document_version_id": str(scope[2]),
                        "generation_id": str(scope[3]),
                        "document_title": content,
                        "content_type": "text/plain",
                        "content": content,
                        "chunk_index": 0,
                    },
                )
            )
        client.upsert(collection_name=collection, points=points, wait=True)
        request = RAGRequest(
            workspace_id=workspace,
            documents=(RAGDocumentScope(document, version, generation, True),),
            query="allowed",
            history=(),
        )
        query_filter = _retrieval_filter(request)
        dense_points = client.query_points(
            collection_name=collection,
            query=[1.0, 0.0],
            query_filter=query_filter,
            limit=10,
            with_payload=True,
        ).points
        sparse_points = client.query_points(
            collection_name=collection,
            query=models.SparseVector(indices=[1], values=[1.0]),
            using=SPARSE_VECTOR_NAME,
            query_filter=query_filter,
            limit=10,
            with_payload=True,
        ).points
        dense_candidates = [_authorized_candidate(point, request) for point in dense_points]
        sparse_candidates = [_authorized_candidate(point, request) for point in sparse_points]

        fused = reciprocal_rank_fusion(dense_candidates, sparse_candidates, k=60)

        assert len(fused) == 1
        assert fused[0].document_id == document
        assert fused[0].content == "allowed"
    finally:
        if client.collection_exists(collection):
            client.delete_collection(collection)
        client.close()
