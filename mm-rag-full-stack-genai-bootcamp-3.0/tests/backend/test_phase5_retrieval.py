from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from qdrant_client import QdrantClient, models

from backend.app.core.config import Settings
from backend.app.rag import engine as engine_module
from backend.app.rag.engine import (
    INSUFFICIENT_EVIDENCE_MARKER,
    INSUFFICIENT_EVIDENCE_MESSAGE,
    QdrantOpenAIRAGEngine,
    RAGDocumentScope,
    RAGRequest,
    RAGUnavailableError,
)


class FakeEmbeddings:
    def __init__(self, **kwargs):
        pass

    def embed_query(self, query):
        return [1.0, 0.0]


class FakeChat:
    def __init__(self, **kwargs):
        pass

    def invoke(self, messages):
        return SimpleNamespace(content="Grounded answer [1].", usage_metadata={})


class FakeAbstainingChat:
    def __init__(self, **kwargs):
        pass

    def invoke(self, messages):
        return SimpleNamespace(content=INSUFFICIENT_EVIDENCE_MARKER, usage_metadata={})


class FakeSparseEncoder:
    def embed_documents(self, texts):
        return ()

    def embed_query(self, query):
        return models.SparseVector(indices=[1], values=[1.0])


class FakeQdrant:
    def __init__(self, dense, sparse, *, sparse_error: bool = False):
        self.dense = dense
        self.sparse = sparse
        self.sparse_error = sparse_error
        self.filters: list[Any] = []

    def collection_exists(self, name):
        return True

    def query_points(self, **kwargs):
        self.filters.append(kwargs["query_filter"])
        if kwargs.get("using"):
            if self.sparse_error:
                raise RuntimeError("sparse unavailable")
            return SimpleNamespace(points=self.sparse)
        return SimpleNamespace(points=self.dense)


def _point(point_id, scope, content, score):
    return SimpleNamespace(
        id=point_id,
        score=score,
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


def _settings(profile="hybrid-v1"):
    return Settings(
        app_env="test",
        openai_api_key=SecretStr("test-key"),
        rag_retrieval_profile=profile,
        rag_sparse_indexing_enabled=False,
    )


def test_hybrid_retrieval_uses_same_filter_and_rrf(monkeypatch) -> None:
    monkeypatch.setattr(engine_module, "OpenAIEmbeddings", FakeEmbeddings)
    monkeypatch.setattr(engine_module, "ChatOpenAI", FakeChat)
    workspace = uuid4()
    first = (workspace, uuid4(), uuid4(), uuid4())
    second = (workspace, uuid4(), uuid4(), uuid4())
    qdrant = FakeQdrant(
        [_point("dense-only", first, "dense", 0.99), _point("shared", second, "shared", 0.1)],
        [_point("shared", second, "shared", 50.0)],
    )
    request = RAGRequest(
        workspace_id=workspace,
        documents=(
            RAGDocumentScope(first[1], first[2], first[3], True),
            RAGDocumentScope(second[1], second[2], second[3], True),
        ),
        query="shared evidence",
        history=(),
    )

    answer = QdrantOpenAIRAGEngine(
        _settings(), cast(QdrantClient, qdrant), sparse_encoder=FakeSparseEncoder()
    ).answer(request)

    assert answer.citations[0].document_id == second[1]
    assert len(qdrant.filters) == 2
    assert qdrant.filters[0].model_dump() == qdrant.filters[1].model_dump()


@pytest.mark.parametrize(
    ("query", "expected_weights"),
    (("find ACME-774", (1.0, 1.0)), ("how does renewal work", (2.0, 1.0))),
)
def test_hybrid_v2_uses_only_frozen_query_signal_policy(
    monkeypatch, query: str, expected_weights: tuple[float, float]
) -> None:
    monkeypatch.setattr(engine_module, "OpenAIEmbeddings", FakeEmbeddings)
    monkeypatch.setattr(engine_module, "ChatOpenAI", FakeChat)
    original_fusion = engine_module.reciprocal_rank_fusion
    observed: dict[str, float] = {}

    def capture_fusion(dense, sparse, **kwargs):
        observed.update(kwargs)
        return original_fusion(dense, sparse, **kwargs)

    monkeypatch.setattr(engine_module, "reciprocal_rank_fusion", capture_fusion)
    workspace, document, version, generation = uuid4(), uuid4(), uuid4(), uuid4()
    scope = (workspace, document, version, generation)
    point = _point("shared", scope, "authorized evidence", 1.0)
    qdrant = FakeQdrant([point], [point])
    request = RAGRequest(
        workspace_id=workspace,
        documents=(RAGDocumentScope(document, version, generation, True),),
        query=query,
        history=(),
    )

    QdrantOpenAIRAGEngine(
        _settings("hybrid-v2"),
        cast(QdrantClient, qdrant),
        sparse_encoder=FakeSparseEncoder(),
    ).answer(request)

    assert (observed["dense_weight"], observed["sparse_weight"]) == expected_weights
    assert qdrant.filters[0].model_dump() == qdrant.filters[1].model_dump()


def test_sparse_failure_returns_authorized_dense_order(monkeypatch) -> None:
    monkeypatch.setattr(engine_module, "OpenAIEmbeddings", FakeEmbeddings)
    monkeypatch.setattr(engine_module, "ChatOpenAI", FakeChat)
    workspace, document, version, generation = uuid4(), uuid4(), uuid4(), uuid4()
    scope = (workspace, document, version, generation)
    qdrant = FakeQdrant([_point("dense", scope, "dense fallback", 0.9)], [], sparse_error=True)
    request = RAGRequest(
        workspace_id=workspace,
        documents=(RAGDocumentScope(document, version, generation, True),),
        query="question",
        history=(),
    )

    answer = QdrantOpenAIRAGEngine(
        _settings(), cast(QdrantClient, qdrant), sparse_encoder=FakeSparseEncoder()
    ).answer(request)

    assert answer.citations[0].excerpt == "dense fallback"


def test_grounded_answer_abstains_without_citations(monkeypatch) -> None:
    monkeypatch.setattr(engine_module, "OpenAIEmbeddings", FakeEmbeddings)
    monkeypatch.setattr(engine_module, "ChatOpenAI", FakeAbstainingChat)
    workspace, document, version, generation = uuid4(), uuid4(), uuid4(), uuid4()
    scope = (workspace, document, version, generation)
    request = RAGRequest(
        workspace_id=workspace,
        documents=(RAGDocumentScope(document, version, generation, False),),
        query="What is not stated in this evidence?",
        history=(),
    )

    answer = QdrantOpenAIRAGEngine(
        _settings("dense-v1"),
        cast(QdrantClient, FakeQdrant([_point("dense", scope, "related", 0.9)], [])),
    ).answer(request)

    assert answer.content == INSUFFICIENT_EVIDENCE_MESSAGE
    assert answer.citations == ()


def test_mixed_generation_scope_uses_dense_only(monkeypatch) -> None:
    monkeypatch.setattr(engine_module, "OpenAIEmbeddings", FakeEmbeddings)
    monkeypatch.setattr(engine_module, "ChatOpenAI", FakeChat)
    workspace = uuid4()
    first = (workspace, uuid4(), uuid4(), uuid4())
    second = (workspace, uuid4(), uuid4(), uuid4())
    qdrant = FakeQdrant([_point("dense", first, "dense", 0.9)], [])
    request = RAGRequest(
        workspace_id=workspace,
        documents=(
            RAGDocumentScope(first[1], first[2], first[3], True),
            RAGDocumentScope(second[1], second[2], second[3], False),
        ),
        query="question",
        history=(),
    )

    QdrantOpenAIRAGEngine(
        _settings(), cast(QdrantClient, qdrant), sparse_encoder=FakeSparseEncoder()
    ).answer(request)

    assert len(qdrant.filters) == 1


def test_sparse_result_identity_is_revalidated(monkeypatch) -> None:
    monkeypatch.setattr(engine_module, "OpenAIEmbeddings", FakeEmbeddings)
    workspace, document, version, generation = uuid4(), uuid4(), uuid4(), uuid4()
    scope = (workspace, document, version, generation)
    unsafe = _point("unsafe", scope, "unsafe", 1.0)
    unsafe.payload["workspace_id"] = str(UUID(int=0))
    qdrant = FakeQdrant([_point("dense", scope, "dense", 1.0)], [unsafe])
    request = RAGRequest(
        workspace_id=workspace,
        documents=(RAGDocumentScope(document, version, generation, True),),
        query="question",
        history=(),
    )

    with pytest.raises(RAGUnavailableError, match="authorization"):
        QdrantOpenAIRAGEngine(
            _settings(), cast(QdrantClient, qdrant), sparse_encoder=FakeSparseEncoder()
        ).answer(request)
