from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from qdrant_client import QdrantClient

from backend.app.core.config import Settings
from backend.app.rag import engine as engine_module
from backend.app.rag.engine import (
    QdrantOpenAIRAGEngine,
    RAGDocumentScope,
    RAGRequest,
)
from backend.app.retrieval.ranking import RetrievalCandidate
from backend.app.visual.embedding import (
    VISUAL_EMBEDDING_PROFILE,
    VISUAL_VECTOR_SIZE,
    visual_embedding_fingerprint,
)
from backend.app.visual.indexing import (
    QdrantVisualRegionIndexer,
    VisualIndexingRequest,
    VisualRegionIndexItem,
)
from backend.app.visual.retrieval import (
    TEXT_ONLY_ROUTE,
    VISUAL_ROUTE,
    QdrantVisualRetriever,
    VisualDocumentScope,
    VisualRetrievalError,
    VisualSearchRequest,
    select_visual_route,
    visual_retrieval_fingerprint,
)


class FakeVisualEncoder:
    def embed_images(self, images):
        return tuple(_vector() for _ in images)

    def embed_query(self, query):
        return _vector()


class FakeOpenAIEmbeddings:
    def __init__(self, **kwargs):
        pass

    def embed_query(self, query):
        return [1.0, 0.0]


class FakeChat:
    def __init__(self, **kwargs):
        pass

    def invoke(self, messages):
        return SimpleNamespace(content="Grounded answer [1].", usage_metadata={})


class TextQdrant:
    def __init__(self, point):
        self.point = point
        self.calls = 0

    def collection_exists(self, name):
        return True

    def query_points(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(points=[self.point])


class StubVisualRetriever:
    def __init__(self, candidate=None, *, failure: bool = False):
        self.candidate = candidate
        self.failure = failure
        self.calls = 0

    def retrieve(self, request):
        self.calls += 1
        if self.failure:
            raise VisualRetrievalError("unavailable")
        return [self.candidate] if self.candidate is not None else []


def _vector() -> tuple[float, ...]:
    return (1.0, *(0.0 for _ in range(VISUAL_VECTOR_SIZE - 1)))


def _settings(**overrides) -> Settings:
    return Settings(
        app_env="test",
        openai_api_key=SecretStr("test-key"),
        rag_retrieval_profile="dense-v1",
        rag_sparse_indexing_enabled=False,
        phase6_profile="visual-table-v1",
        **overrides,
    )


def _text_point(scope, *, point_id="text-point"):
    return SimpleNamespace(
        id=point_id,
        score=0.9,
        payload={
            "tenant_id": str(scope[0]),
            "workspace_id": str(scope[0]),
            "document_id": str(scope[1]),
            "document_version_id": str(scope[2]),
            "generation_id": str(scope[3]),
            "document_title": "Report",
            "content_type": "text/plain",
            "content": "Text evidence",
            "chunk_index": 0,
        },
    )


def test_visual_index_and_retrieval_preserve_complete_scope() -> None:
    settings = _settings(phase6_visual_collection_name="phase6_visual_test")
    qdrant = QdrantClient(":memory:")
    indexer = QdrantVisualRegionIndexer(settings, qdrant, FakeVisualEncoder())
    workspace, document, version, generation, region = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    result = indexer.index(
        VisualIndexingRequest(
            workspace_id=workspace,
            document_id=document,
            document_version_id=version,
            generation_id=generation,
            document_title="Quarterly report",
            regions=(
                VisualRegionIndexItem(
                    region_id=region,
                    page_number=2,
                    region_kind="chart",
                    image=b"fixture-image",
                    content="Revenue chart on page 2.",
                ),
            ),
        )
    )

    assert result.vector_count == 1
    assert result.profile == VISUAL_EMBEDDING_PROFILE
    candidates = QdrantVisualRetriever(settings, qdrant, FakeVisualEncoder()).retrieve(
        VisualSearchRequest(
            workspace_id=workspace,
            documents=(VisualDocumentScope(document, version, generation),),
            query="What does the revenue chart show?",
        )
    )
    assert len(candidates) == 1
    assert candidates[0].region_id == region
    assert candidates[0].generation_id == generation
    assert candidates[0].evidence_kind == "chart"


def test_visual_result_scope_is_revalidated() -> None:
    settings = _settings()
    workspace, document, version, generation, region = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    point = SimpleNamespace(
        id=str(region),
        score=0.8,
        payload={
            "tenant_id": str(UUID(int=0)),
            "workspace_id": str(workspace),
            "document_id": str(document),
            "document_version_id": str(version),
            "generation_id": str(generation),
            "region_id": str(region),
            "region_kind": "figure",
            "page_number": 1,
            "vector_profile": VISUAL_EMBEDDING_PROFILE,
            "vector_profile_fingerprint": visual_embedding_fingerprint(batch_size=8),
            "payload_schema_revision": 1,
        },
    )
    qdrant = SimpleNamespace(
        collection_exists=lambda name: True,
        query_points=lambda **kwargs: SimpleNamespace(points=[point]),
    )
    with pytest.raises(VisualRetrievalError, match="authorization"):
        QdrantVisualRetriever(
            settings,
            cast(QdrantClient, qdrant),
            FakeVisualEncoder(),
        ).retrieve(
            VisualSearchRequest(
                workspace,
                (VisualDocumentScope(document, version, generation),),
                "show the figure",
            )
        )


@pytest.mark.parametrize(
    ("query", "route"),
    (("Summarize the policy", TEXT_ONLY_ROUTE), ("What does the diagram show?", VISUAL_ROUTE)),
)
def test_visual_router_is_query_only_and_deterministic(query: str, route: str) -> None:
    assert select_visual_route(query) == route
    assert select_visual_route(query) == route


def test_rag_always_runs_text_and_adds_visual_only_for_signaled_query(monkeypatch) -> None:
    monkeypatch.setattr(engine_module, "OpenAIEmbeddings", FakeOpenAIEmbeddings)
    monkeypatch.setattr(engine_module, "ChatOpenAI", FakeChat)
    workspace, document, version, generation, region = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    text_qdrant = TextQdrant(_text_point((workspace, document, version, generation)))
    visual = StubVisualRetriever(
        RetrievalCandidate(
            point_id=f"visual:{region}",
            document_id=document,
            document_version_id=version,
            generation_id=generation,
            document_title="Report",
            content_type="image/png",
            content="Revenue chart on page 2.",
            page_number=2,
            chunk_index=0,
            score=0.8,
            evidence_kind="chart",
            region_id=region,
        )
    )
    engine = QdrantOpenAIRAGEngine(
        _settings(),
        cast(QdrantClient, text_qdrant),
        visual_retriever=visual,
    )
    scope = (RAGDocumentScope(document, version, generation),)

    ordinary = engine.answer(RAGRequest(workspace, scope, "Summarize the report", ()))
    chart = engine.answer(RAGRequest(workspace, scope, "Explain the chart", ()))

    assert ordinary.citations[0].evidence_kind == "text"
    assert visual.calls == 1
    assert text_qdrant.calls == 2
    assert any(citation.region_id == region for citation in chart.citations)


def test_visual_failure_falls_back_to_authorized_text(monkeypatch) -> None:
    monkeypatch.setattr(engine_module, "OpenAIEmbeddings", FakeOpenAIEmbeddings)
    monkeypatch.setattr(engine_module, "ChatOpenAI", FakeChat)
    workspace, document, version, generation = uuid4(), uuid4(), uuid4(), uuid4()
    qdrant = TextQdrant(_text_point((workspace, document, version, generation)))
    visual = StubVisualRetriever(failure=True)
    answer = QdrantOpenAIRAGEngine(
        _settings(),
        cast(QdrantClient, qdrant),
        visual_retriever=visual,
    ).answer(
        RAGRequest(
            workspace,
            (RAGDocumentScope(document, version, generation),),
            "Explain the figure",
            (),
        )
    )

    assert visual.calls == 1
    assert [citation.excerpt for citation in answer.citations] == ["Text evidence"]


def test_visual_profile_fingerprint_changes_with_candidate_bounds() -> None:
    first = visual_retrieval_fingerprint(_settings(phase6_visual_candidate_limit=12))
    second = visual_retrieval_fingerprint(_settings(phase6_visual_candidate_limit=13))
    assert first != second
