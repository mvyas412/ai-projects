import asyncio
import json
from contextlib import closing
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from openai import APIError
from pydantic import SecretStr
from qdrant_client import QdrantClient

from backend.app.core.config import Settings
from backend.app.ingestion.pipeline import pipeline_fingerprint
from backend.app.rag import engine as engine_module
from backend.app.rag import indexing as indexing_module
from backend.app.rag.engine import QdrantOpenAIRAGEngine, RAGDocumentScope, RAGRequest
from backend.app.rag.indexing import IndexingRequest, QdrantOpenAIDocumentIndexer
from scripts.phase11_retry_controls import main, retry_report


def test_configuration_report_is_content_free_and_not_execution_authority() -> None:
    report = retry_report(
        Settings(
            openai_api_key=SecretStr("private-synthetic-key"),
            execution_retry_profile="pilot-single-attempt-v1",
        )
    )
    assert report == {
        "profile": "pilot-single-attempt-v1",
        "ingestion_max_attempts": 1,
        "embedding_max_retries": 0,
        "chat_max_retries": 0,
        "bounded_retry_configuration": True,
        "live_execution_authorized": False,
    }


def test_configuration_error_does_not_disclose_environment_values(monkeypatch, capsys) -> None:
    monkeypatch.setenv("EXECUTION_RETRY_PROFILE", "private-invalid-profile")
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "status": "invalid_configuration",
        "live_execution_authorized": False,
    }


@pytest.mark.parametrize(
    ("profile", "embedding_retries", "chat_retries"),
    [("standard", 2, None), ("pilot-single-attempt-v1", 0, 0)],
)
def test_all_product_provider_clients_receive_the_selected_retry_profile(
    monkeypatch, profile, embedding_retries, chat_retries
) -> None:
    embeddings_options = []
    chat_options = []

    class Embeddings:
        def __init__(self, **kwargs):
            embeddings_options.append(kwargs)

        def embed_documents(self, texts):
            return [[1.0, 0.0] for _ in texts]

        def embed_query(self, query):
            return [1.0, 0.0]

    class Chat:
        def __init__(self, **kwargs):
            chat_options.append(kwargs)

        def invoke(self, messages):
            return SimpleNamespace(content="Grounded answer [1].", usage_metadata={})

    monkeypatch.setattr(indexing_module, "OpenAIEmbeddings", Embeddings)
    monkeypatch.setattr(engine_module, "OpenAIEmbeddings", Embeddings)
    monkeypatch.setattr(indexing_module, "ChatOpenAI", Chat)
    monkeypatch.setattr(engine_module, "ChatOpenAI", Chat)
    settings = Settings(
        app_env="test",
        openai_api_key=SecretStr("synthetic-key"),
        execution_retry_profile=profile,
        rag_sparse_indexing_enabled=False,
        rag_retrieval_profile="dense-v1",
        phase6_profile="disabled",
    )
    request = IndexingRequest(
        workspace_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        generation_id=uuid4(),
        document_title="Fixture",
        media_type="text/plain",
        content=b"Authorized synthetic evidence.",
    )
    with closing(QdrantClient(":memory:")) as qdrant:
        QdrantOpenAIDocumentIndexer(settings, qdrant).index(request)
        answer = QdrantOpenAIRAGEngine(settings, qdrant).answer(
            RAGRequest(
                workspace_id=request.workspace_id,
                documents=(
                    RAGDocumentScope(
                        request.document_id, request.document_version_id, request.generation_id
                    ),
                ),
                query="Explain the evidence",
                history=(),
            )
        )
        assert answer.citations[0].document_id == request.document_id
    image_request = IndexingRequest(
        workspace_id=request.workspace_id,
        document_id=request.document_id,
        document_version_id=request.document_version_id,
        document_title="Fixture",
        media_type="image/png",
        content=b"synthetic-image",
    )
    indexing_module._extract_pages(image_request, SecretStr("synthetic-key"), settings)
    assert len(embeddings_options) == len(chat_options) == 2
    assert all(option["max_retries"] == embedding_retries for option in embeddings_options)
    assert all(option["max_retries"] == chat_retries for option in chat_options)
    assert pipeline_fingerprint(settings, "application/pdf") == pipeline_fingerprint(
        settings.model_copy(update={"execution_retry_profile": "standard"}), "application/pdf"
    )


@pytest.mark.parametrize("kind", ["embedding", "chat"])
@pytest.mark.parametrize("failure", ["429", "503", "connection", "timeout"])
def test_installed_sdk_makes_one_wire_attempt_on_failure(kind, failure) -> None:
    calls = []

    def fail(request):
        calls.append(request.url.path)
        if failure == "connection":
            raise httpx.ConnectError("synthetic connection failure", request=request)
        if failure == "timeout":
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        return httpx.Response(int(failure), json={"error": {"message": "synthetic failure"}})

    transport = httpx.MockTransport(fail)
    with httpx.Client(transport=transport, trust_env=False) as client:
        async_client = httpx.AsyncClient(transport=transport, trust_env=False)
        try:
            if kind == "embedding":
                provider = OpenAIEmbeddings(
                    api_key=SecretStr("synthetic-key"),
                    max_retries=0,
                    base_url="https://provider.invalid/v1",
                    check_embedding_ctx_length=False,
                    http_client=client,
                    http_async_client=async_client,
                )
                with pytest.raises(APIError):
                    provider.embed_query("synthetic query")
            else:
                chat = ChatOpenAI(
                    api_key=SecretStr("synthetic-key"),
                    max_retries=0,
                    base_url="https://provider.invalid/v1",
                    model="gpt-4.1-mini",
                    http_client=client,
                    http_async_client=async_client,
                )
                with pytest.raises(APIError):
                    chat.invoke([HumanMessage(content="synthetic query")])
            assert len(calls) == 1
        finally:
            asyncio.run(async_client.aclose())
