from __future__ import annotations

import base64
import hashlib
from collections.abc import Callable
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
from backend.app.retrieval.sparse import (
    SPARSE_VECTOR_NAME,
    FastEmbedBM25Encoder,
    SparseEncoder,
)

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
    generation_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class IndexingResult:
    chunk_count: int
    vector_count: int | None = None
    sparse_vector_count: int = 0


IndexingProgress = Callable[[str, int | None, int | None, str | None], None]


class DocumentIndexer(Protocol):
    def index(
        self, request: IndexingRequest, *, progress: IndexingProgress | None = None
    ) -> IndexingResult: ...


class UnavailableDocumentIndexer:
    def index(
        self, request: IndexingRequest, *, progress: IndexingProgress | None = None
    ) -> IndexingResult:
        raise IndexingUnavailableError("Document indexing is not configured")


class QdrantOpenAIDocumentIndexer:
    def __init__(
        self,
        settings: Settings,
        qdrant: QdrantClient,
        sparse_encoder: SparseEncoder | None = None,
    ) -> None:
        self._settings = settings
        self._qdrant = qdrant
        self._sparse_encoder = sparse_encoder

    def index(
        self, request: IndexingRequest, *, progress: IndexingProgress | None = None
    ) -> IndexingResult:
        api_key = self._settings.openai_api_key
        if api_key is None:
            raise IndexingUnavailableError("Document indexing is not configured")
        try:
            _notify(progress, "extracting")
            pages = _extract_pages(request, api_key, self._settings)
            _notify(progress, "chunking", 0, len(pages), "pages")
            chunks = _chunk_pages(pages)
            if not chunks:
                raise EmptyDocumentError("No readable content was found in the document")
            _notify(progress, "embedding", 0, len(chunks), "chunks")
            embeddings = OpenAIEmbeddings(
                api_key=api_key,
                model=self._settings.openai_embedding_model,
            ).embed_documents([content for content, _ in chunks])
            sparse_vectors = (
                self._sparse_encoder.embed_documents([content for content, _ in chunks])
                if self._sparse_encoder is not None
                else ()
            )
            if sparse_vectors and len(sparse_vectors) != len(chunks):
                raise RuntimeError("Sparse encoder returned an invalid result count")
            self._ensure_collection(len(embeddings[0]), sparse_enabled=bool(sparse_vectors))
            scope = VectorScope(
                request.workspace_id,
                request.document_id,
                request.document_version_id,
                request.generation_id,
            )
            if request.generation_id is None:
                # Preserve the accepted synchronous compatibility path. Async workers
                # always provide a generation and never delete-before-replace.
                self._qdrant.delete(
                    collection_name=self._settings.qdrant_collection_name,
                    points_selector=models.FilterSelector(filter=scope.filter()),
                    wait=True,
                )
            _notify(progress, "writing_outputs", 0, len(chunks), "vectors")
            points = [
                models.PointStruct(
                    id=str(
                        uuid5(
                            POINT_NAMESPACE,
                            _point_identity(request, content, page_number, index),
                        )
                    ),
                    vector=(
                        {
                            "": vector,
                            SPARSE_VECTOR_NAME: sparse_vectors[index],
                        }
                        if sparse_vectors
                        else vector
                    ),
                    payload={
                        **scope.payload(),
                        "document_title": request.document_title,
                        "content_type": request.media_type,
                        "content": content,
                        "page_number": page_number,
                        "chunk_index": index,
                        "sparse_profile": (
                            SPARSE_VECTOR_NAME if sparse_vectors else None
                        ),
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
            _notify(progress, "validating", len(points), len(points), "vectors")
            return IndexingResult(
                chunk_count=len(points),
                vector_count=len(points),
                sparse_vector_count=len(sparse_vectors),
            )
        except EmptyDocumentError:
            raise
        except Exception as exc:
            raise IndexingUnavailableError(
                "The document indexing service is temporarily unavailable"
            ) from exc

    def _ensure_collection(self, vector_size: int, *, sparse_enabled: bool) -> None:
        name = self._settings.qdrant_collection_name
        if not self._qdrant.collection_exists(name):
            self._qdrant.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=vector_size, distance=models.Distance.COSINE
                ),
                sparse_vectors_config=(
                    {
                        SPARSE_VECTOR_NAME: models.SparseVectorParams(
                            modifier=models.Modifier.IDF
                        )
                    }
                    if sparse_enabled
                    else None
                ),
            )
        elif sparse_enabled:
            info = self._qdrant.get_collection(name)
            sparse_vectors = info.config.params.sparse_vectors or {}
            if SPARSE_VECTOR_NAME not in sparse_vectors:
                # Existing promoted points stay immutable; only the collection schema
                # changes before successor generations publish sparse vectors.
                self._qdrant.update_collection(
                    collection_name=name,
                    sparse_vectors_config={
                        SPARSE_VECTOR_NAME: models.SparseVectorParams(
                            modifier=models.Modifier.IDF
                        )
                    },
                )
        ensure_scope_payload_indexes(self._qdrant, name)


def build_document_indexer(
    settings: Settings, qdrant: QdrantClient
) -> DocumentIndexer:
    if settings.openai_api_key is None:
        return UnavailableDocumentIndexer()
    try:
        sparse_encoder = (
            FastEmbedBM25Encoder(settings.phase5_model_cache_dir)
            if settings.rag_sparse_indexing_enabled
            else None
        )
    except Exception:
        return UnavailableDocumentIndexer()
    return QdrantOpenAIDocumentIndexer(settings, qdrant, sparse_encoder)


def _extract_pages(
    request: IndexingRequest, api_key: SecretStr, settings: Settings
) -> list[tuple[str, int | None]]:
    """Normalize supported formats into page-aware text for one indexing path."""

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


def _point_identity(
    request: IndexingRequest,
    content: str,
    page_number: int | None,
    chunk_index: int,
) -> str:
    content_hash = hashlib.sha256(content.strip().encode("utf-8")).hexdigest()
    generation = request.generation_id or request.document_version_id
    locator = f"page={page_number or 0};chunk={chunk_index};sha256={content_hash}"
    return f"{request.workspace_id}:{request.document_version_id}:{generation}:{locator}"


def _notify(
    progress: IndexingProgress | None,
    stage: str,
    completed: int | None = None,
    total: int | None = None,
    unit: str | None = None,
) -> None:
    if progress is not None:
        progress(stage, completed, total, unit)
