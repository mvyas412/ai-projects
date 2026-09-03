from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

from pydantic import SecretStr
from qdrant_client import QdrantClient, models

from backend.app.core.config import Settings
from backend.app.ingestion.pipeline import manifest_supports_sparse, pipeline_manifest
from backend.app.rag import indexing as indexing_module
from backend.app.rag.indexing import IndexingRequest, QdrantOpenAIDocumentIndexer
from backend.app.retrieval.sparse import SPARSE_VECTOR_NAME


class FakeEmbeddings:
    def __init__(self, **kwargs):
        pass

    def embed_documents(self, texts):
        return [[1.0, 0.0] for _ in texts]


class FakeSparseEncoder:
    def embed_documents(self, texts):
        return tuple(models.SparseVector(indices=[index + 1], values=[1.0]) for index, _ in enumerate(texts))

    def embed_query(self, query):
        return models.SparseVector(indices=[1], values=[1.0])


class FakeQdrant:
    def __init__(self, *, exists=False, sparse_exists=False):
        self.exists = exists
        self.sparse_exists = sparse_exists
        self.created: dict[str, Any] | None = None
        self.updated: dict[str, Any] | None = None
        self.points: list[Any] = []

    def collection_exists(self, name):
        return self.exists

    def create_collection(self, **kwargs):
        self.created = kwargs
        self.exists = True

    def get_collection(self, name):
        sparse = {SPARSE_VECTOR_NAME: object()} if self.sparse_exists else {}
        return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(sparse_vectors=sparse)))

    def update_collection(self, **kwargs):
        self.updated = kwargs
        self.sparse_exists = True

    def create_payload_index(self, *args, **kwargs):
        return object()

    def delete(self, **kwargs):
        pass

    def upsert(self, **kwargs):
        self.points = kwargs["points"]


def _settings():
    return Settings(
        app_env="test",
        openai_api_key=SecretStr("test-key"),
        rag_sparse_indexing_enabled=True,
    )


def _request():
    return IndexingRequest(
        workspace_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        generation_id=uuid4(),
        document_title="Contract",
        media_type="text/plain",
        content=b"Contract ACME-774 renews in 2027.",
    )


def test_successor_generation_writes_dense_and_sparse_atomically(monkeypatch) -> None:
    monkeypatch.setattr(indexing_module, "OpenAIEmbeddings", FakeEmbeddings)
    qdrant = FakeQdrant()

    result = QdrantOpenAIDocumentIndexer(
        _settings(), cast(QdrantClient, qdrant), FakeSparseEncoder()
    ).index(_request())

    assert result.chunk_count == result.vector_count == result.sparse_vector_count == 1
    assert qdrant.created is not None
    assert qdrant.created["sparse_vectors_config"][SPARSE_VECTOR_NAME].modifier == "idf"
    assert set(qdrant.points[0].vector) == {"", SPARSE_VECTOR_NAME}
    assert qdrant.points[0].payload["sparse_profile"] == SPARSE_VECTOR_NAME


def test_existing_collection_adds_schema_without_mutating_points(monkeypatch) -> None:
    monkeypatch.setattr(indexing_module, "OpenAIEmbeddings", FakeEmbeddings)
    qdrant = FakeQdrant(exists=True)

    QdrantOpenAIDocumentIndexer(
        _settings(), cast(QdrantClient, qdrant), FakeSparseEncoder()
    ).index(_request())

    assert qdrant.updated is not None
    assert qdrant.updated["sparse_vectors_config"][SPARSE_VECTOR_NAME].modifier == "idf"
    assert qdrant.points


def test_generation_manifest_requires_complete_pinned_sparse_output() -> None:
    settings = _settings()
    manifest = {
        "pipeline": pipeline_manifest(settings, "text/plain"),
        "chunk_count": 2,
        "sparse_vector_count": 2,
    }

    assert manifest_supports_sparse(manifest) is True
    manifest["sparse_vector_count"] = 1
    assert manifest_supports_sparse(manifest) is False
