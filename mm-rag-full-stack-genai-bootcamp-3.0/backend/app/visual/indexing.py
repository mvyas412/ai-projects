from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from qdrant_client import QdrantClient, models

from backend.app.core.config import Settings
from backend.app.retrieval.scope import VectorScope
from backend.app.visual.embedding import (
    VISUAL_EMBEDDING_PROFILE,
    VISUAL_VECTOR_SIZE,
    VisualEmbeddingEncoder,
    visual_embedding_fingerprint,
)

VISUAL_PAYLOAD_SCHEMA_REVISION = 1
VISUAL_INDEXED_PAYLOAD_FIELDS = (
    "tenant_id",
    "workspace_id",
    "document_id",
    "document_version_id",
    "generation_id",
    "region_id",
    "region_kind",
    "vector_profile",
)


class VisualIndexingError(RuntimeError):
    """Raised when a visual generation cannot be indexed completely."""


@dataclass(frozen=True, slots=True)
class VisualRegionIndexItem:
    region_id: UUID
    page_number: int
    region_kind: str
    image: bytes
    content: str


@dataclass(frozen=True, slots=True)
class VisualIndexingRequest:
    workspace_id: UUID
    document_id: UUID
    document_version_id: UUID
    generation_id: UUID
    document_title: str
    regions: tuple[VisualRegionIndexItem, ...]


@dataclass(frozen=True, slots=True)
class VisualIndexingResult:
    vector_count: int
    profile: str
    profile_fingerprint: str


class VisualRegionIndexer(Protocol):
    def index(self, request: VisualIndexingRequest) -> VisualIndexingResult: ...


class QdrantVisualRegionIndexer:
    def __init__(
        self,
        settings: Settings,
        qdrant: QdrantClient,
        encoder: VisualEmbeddingEncoder,
    ) -> None:
        self._settings = settings
        self._qdrant = qdrant
        self._encoder = encoder

    def index(self, request: VisualIndexingRequest) -> VisualIndexingResult:
        fingerprint = visual_embedding_fingerprint(
            batch_size=self._settings.phase6_visual_embedding_batch_size
        )
        if not request.regions:
            return VisualIndexingResult(0, VISUAL_EMBEDDING_PROFILE, fingerprint)
        try:
            vectors = self._encoder.embed_images([item.image for item in request.regions])
            if len(vectors) != len(request.regions):
                raise VisualIndexingError("Visual encoder returned an invalid result count")
            self._ensure_collection()
            scope = VectorScope(
                request.workspace_id,
                request.document_id,
                request.document_version_id,
                request.generation_id,
            )
            points = [
                models.PointStruct(
                    id=str(item.region_id),
                    vector=list(vector),
                    payload={
                        **scope.payload(),
                        "document_title": request.document_title,
                        "content_type": "image/png",
                        "content": item.content[:2000],
                        "page_number": item.page_number,
                        "region_id": str(item.region_id),
                        "region_kind": item.region_kind,
                        "vector_profile": VISUAL_EMBEDDING_PROFILE,
                        "vector_profile_fingerprint": fingerprint,
                        "payload_schema_revision": VISUAL_PAYLOAD_SCHEMA_REVISION,
                    },
                )
                for item, vector in zip(request.regions, vectors, strict=True)
            ]
            self._qdrant.upsert(
                collection_name=self._settings.phase6_visual_collection_name,
                points=points,
                wait=True,
            )
            return VisualIndexingResult(len(points), VISUAL_EMBEDDING_PROFILE, fingerprint)
        except VisualIndexingError:
            raise
        except Exception as exc:
            raise VisualIndexingError("Visual indexing is temporarily unavailable") from exc

    def _ensure_collection(self) -> None:
        name = self._settings.phase6_visual_collection_name
        if not self._qdrant.collection_exists(name):
            self._qdrant.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=VISUAL_VECTOR_SIZE,
                    distance=models.Distance.COSINE,
                ),
            )
        else:
            info = self._qdrant.get_collection(name)
            vectors = info.config.params.vectors
            if not isinstance(vectors, models.VectorParams):
                raise VisualIndexingError("Visual collection vector schema is incompatible")
            if vectors.size != VISUAL_VECTOR_SIZE or vectors.distance != models.Distance.COSINE:
                raise VisualIndexingError("Visual collection vector schema is incompatible")
        ensure_visual_payload_indexes(self._qdrant, name)


def ensure_visual_payload_indexes(qdrant: QdrantClient, collection_name: str) -> None:
    for field in VISUAL_INDEXED_PAYLOAD_FIELDS:
        qdrant.create_payload_index(
            collection_name=collection_name,
            field_name=field,
            field_schema=(
                models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD, is_tenant=True)
                if field == "tenant_id"
                else models.PayloadSchemaType.KEYWORD
            ),
            wait=True,
        )
    qdrant.create_payload_index(
        collection_name=collection_name,
        field_name="page_number",
        field_schema=models.PayloadSchemaType.INTEGER,
        wait=True,
    )
