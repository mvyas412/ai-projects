from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol
from uuid import UUID, uuid5

from docx import Document as DocxDocument
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import SecretStr
from pypdf import PdfReader
from qdrant_client import QdrantClient, models

from backend.app.core.config import Settings
from backend.app.retrieval.scope import VectorScope, ensure_scope_payload_indexes

POINT_NAMESPACE = UUID("21ea46fc-d41b-49eb-b30a-3724c21befab")


class IndexingUnavailableError(Exception):
    """Raised when indexing is not configured or a dependency is unavailable."""


class EmptyDocumentError(Exception):
    """Raised when no meaningful content can be extracted."""


@dataclass(frozen=True, slots=True)
class IndexingRequest:
    workspace_id: UUID
    document_id: UUID
    document_version_id: UUID
    document_title: str
    media_type: str
    content: bytes


@dataclass(frozen=True, slots=True)
class IndexingResult:
    chunk_count: int


class DocumentIndexer(Protocol):
    def index(self, request: IndexingRequest) -> IndexingResult: ...


class UnavailableDocumentIndexer:
    def index(self, request: IndexingRequest) -> IndexingResult:
        raise IndexingUnavailableError("Document indexing is not configured")


class QdrantOpenAIDocumentIndexer:
    def __init__(self, settings: Settings, qdrant: QdrantClient) -> None:
        self._settings = settings
        self._qdrant = qdrant

    def index(self, request: IndexingRequest) -> IndexingResult:
        api_key = self._settings.openai_api_key
        if api_key is None:
            raise IndexingUnavailableError("Document indexing is not configured")
        try:
            pages = _extract_pages(request, api_key, self._settings)
            chunks = _chunk_pages(pages)
            if not chunks:
                raise EmptyDocumentError("No readable content was found in the document")
            embeddings = OpenAIEmbeddings(
                api_key=api_key,
                model=self._settings.openai_embedding_model,
            ).embed_documents([content for content, _ in chunks])
            self._ensure_collection(len(embeddings[0]))
            scope = VectorScope(
                request.workspace_id, request.document_id, request.document_version_id
            )
            self._qdrant.delete(
                collection_name=self._settings.qdrant_collection_name,
                points_selector=models.FilterSelector(filter=scope.filter()),
                wait=True,
            )
            points = [
                models.PointStruct(
                    id=str(
                        uuid5(
                            POINT_NAMESPACE,
                            f"{request.document_version_id}:{index}",
                        )
                    ),
                    vector=vector,
                    payload={
                        **scope.payload(),
                        "document_title": request.document_title,
                        "content_type": request.media_type,
                        "content": content,
                        "page_number": page_number,
                        "chunk_index": index,
                    },
                )
                for index, ((content, page_number), vector) in enumerate(
                    zip(chunks, embeddings, strict=True)
                )
            ]
            self._qdrant.upsert(
                collection_name=self._settings.qdrant_collection_name,
                points=points,
                wait=True,
            )
            return IndexingResult(chunk_count=len(points))
        except EmptyDocumentError:
            raise
        except Exception as exc:
            raise IndexingUnavailableError(
                "The document indexing service is temporarily unavailable"
            ) from exc

    def _ensure_collection(self, vector_size: int) -> None:
        name = self._settings.qdrant_collection_name
        if not self._qdrant.collection_exists(name):
            self._qdrant.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=vector_size, distance=models.Distance.COSINE
                ),
            )
        ensure_scope_payload_indexes(self._qdrant, name)


def build_document_indexer(
    settings: Settings, qdrant: QdrantClient
) -> DocumentIndexer:
    if settings.openai_api_key is None:
        return UnavailableDocumentIndexer()
    return QdrantOpenAIDocumentIndexer(settings, qdrant)


def _extract_pages(
    request: IndexingRequest, api_key: SecretStr, settings: Settings
) -> list[tuple[str, int | None]]:
    if request.media_type == "application/pdf":
        reader = PdfReader(BytesIO(request.content))
        return [
            (text, page_number)
            for page_number, page in enumerate(reader.pages, start=1)
            if (text := (page.extract_text() or "").strip())
        ]
    if request.media_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        document = DocxDocument(BytesIO(request.content))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs).strip()
        return [(text, None)] if text else []
    if request.media_type.startswith("text/"):
        text = request.content.decode("utf-8", errors="replace").strip()
        return [(text, None)] if text else []
    if request.media_type.startswith("image/"):
        encoded = base64.b64encode(request.content).decode("ascii")
        response = ChatOpenAI(
            api_key=api_key,
            model=settings.openai_chat_model,
            temperature=0,
        ).invoke(
            [
                HumanMessage(
                    content=[
                        {
                            "type": "text",
                            "text": (
                                "Transcribe all visible text and describe the factual "
                                "content of this image for document retrieval."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{request.media_type};base64,{encoded}"
                            },
                        },
                    ]
                )
            ]
        )
        text = str(response.content).strip()
        return [(text, 1)] if text else []
    return []


def _chunk_pages(
    pages: list[tuple[str, int | None]],
) -> list[tuple[str, int | None]]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=180)
    return [
        (chunk, page_number)
        for text, page_number in pages
        for chunk in splitter.split_text(text)
        if chunk.strip()
    ]
