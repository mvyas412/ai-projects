from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from qdrant_client import QdrantClient, models

from backend.app.core.config import Settings
from backend.app.retrieval.ranking import RetrievalCandidate
from backend.app.retrieval.scope import workspace_filter
from backend.app.visual.embedding import (
    VISUAL_EMBEDDING_PROFILE,
    VisualEmbeddingEncoder,
    visual_embedding_fingerprint,
)
from backend.app.visual.indexing import VISUAL_PAYLOAD_SCHEMA_REVISION

VISUAL_ROUTER_REVISION = "visual-intent-router-v1"
VISUAL_FUSION_REVISION = "visual-text-rrf-v1"
VISUAL_ROUTE = "text-and-visual"
TEXT_ONLY_ROUTE = "text-only"
_VISUAL_TERMS = re.compile(
    r"\b(?:figure|fig\.?|diagram|image|illustration|photo|photograph|chart|graph|plot|"
    r"axis|axes|legend|visual|flowchart|schematic|shown|depicted|above|below|left|right|"
    r"color|colour|shape)\b",
    re.IGNORECASE,
)


class VisualRetrievalError(RuntimeError):
    """Raised when visual candidates cannot be produced safely."""


@dataclass(frozen=True, slots=True)
class VisualDocumentScope:
    document_id: UUID
    document_version_id: UUID
    generation_id: UUID


@dataclass(frozen=True, slots=True)
class VisualSearchRequest:
    workspace_id: UUID
    documents: tuple[VisualDocumentScope, ...]
    query: str


class VisualRetriever(Protocol):
    def retrieve(self, request: VisualSearchRequest) -> list[RetrievalCandidate]: ...


class QdrantVisualRetriever:
    def __init__(
        self,
        settings: Settings,
        qdrant: QdrantClient,
        encoder: VisualEmbeddingEncoder,
    ) -> None:
        self._settings = settings
        self._qdrant = qdrant
        self._encoder = encoder

    def retrieve(self, request: VisualSearchRequest) -> list[RetrievalCandidate]:
        if not request.documents or len(request.documents) > 100:
            raise VisualRetrievalError("Authorized visual retrieval scope is invalid")
        identities = {
            (scope.document_id, scope.document_version_id, scope.generation_id)
            for scope in request.documents
        }
        if len(identities) != len(request.documents):
            raise VisualRetrievalError("Authorized visual retrieval scope is invalid")
        try:
            if not self._qdrant.collection_exists(self._settings.phase6_visual_collection_name):
                return []
            vector = self._encoder.embed_query(request.query)
            points = self._qdrant.query_points(
                collection_name=self._settings.phase6_visual_collection_name,
                query=list(vector),
                query_filter=_visual_filter(request),
                limit=self._settings.phase6_visual_candidate_limit,
                with_payload=True,
            ).points
            candidates = [_authorized_visual_candidate(point, request, self._settings) for point in points]
        except VisualRetrievalError:
            raise
        except Exception as exc:
            raise VisualRetrievalError("Visual retrieval is temporarily unavailable") from exc
        seen: set[UUID] = set()
        deduplicated: list[RetrievalCandidate] = []
        for candidate in candidates:
            if candidate.region_id in seen:
                continue
            if candidate.region_id is None:
                raise VisualRetrievalError("Visual result omitted region identity")
            seen.add(candidate.region_id)
            deduplicated.append(candidate)
        return deduplicated


def select_visual_route(query: str) -> str:
    normalized = " ".join(query.split())
    return VISUAL_ROUTE if _VISUAL_TERMS.search(normalized) else TEXT_ONLY_ROUTE


def visual_retrieval_fingerprint(settings: Settings) -> str:
    payload = {
        "router_revision": VISUAL_ROUTER_REVISION,
        "visual_pattern": _VISUAL_TERMS.pattern,
        "routes": {"default": TEXT_ONLY_ROUTE, "signaled": VISUAL_ROUTE},
        "fusion_revision": VISUAL_FUSION_REVISION,
        "fusion_k": settings.phase6_visual_fusion_k,
        "candidate_limit": settings.phase6_visual_candidate_limit,
        "final_evidence_limit": settings.rag_retrieval_limit,
        "max_candidates_per_document": settings.rag_max_candidates_per_document,
        "embedding": visual_embedding_fingerprint(
            batch_size=settings.phase6_visual_embedding_batch_size
        ),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _visual_filter(request: VisualSearchRequest) -> models.Filter:
    base = workspace_filter(request.workspace_id)
    document_conditions = [
        models.Filter(
            must=[
                _match("document_id", scope.document_id),
                _match("document_version_id", scope.document_version_id),
                _match("generation_id", scope.generation_id),
            ]
        )
        for scope in request.documents
    ]
    return models.Filter(
        must=[
            *(base.must or []),
            _match("vector_profile", VISUAL_EMBEDDING_PROFILE),
            models.Filter(should=document_conditions),  # type: ignore[arg-type]
        ]
    )


def _authorized_visual_candidate(
    point: Any,
    request: VisualSearchRequest,
    settings: Settings,
) -> RetrievalCandidate:
    payload = point.payload or {}
    try:
        workspace_id = UUID(str(payload["workspace_id"]))
        tenant_id = UUID(str(payload["tenant_id"]))
        document_id = UUID(str(payload["document_id"]))
        version_id = UUID(str(payload["document_version_id"]))
        generation_id = UUID(str(payload["generation_id"]))
        region_id = UUID(str(payload["region_id"]))
        page_number = int(payload["page_number"])
        score = float(point.score)
        schema_revision = int(payload["payload_schema_revision"])
    except (KeyError, TypeError, ValueError) as exc:
        raise VisualRetrievalError("Visual result failed authorization validation") from exc
    allowed = {
        (scope.document_id, scope.document_version_id, scope.generation_id)
        for scope in request.documents
    }
    expected_fingerprint = visual_embedding_fingerprint(
        batch_size=settings.phase6_visual_embedding_batch_size
    )
    if (
        workspace_id != request.workspace_id
        or tenant_id != request.workspace_id
        or (document_id, version_id, generation_id) not in allowed
        or str(point.id) != str(region_id)
        or page_number <= 0
        or payload.get("vector_profile") != VISUAL_EMBEDDING_PROFILE
        or payload.get("vector_profile_fingerprint") != expected_fingerprint
        or schema_revision != VISUAL_PAYLOAD_SCHEMA_REVISION
    ):
        raise VisualRetrievalError("Visual result failed authorization validation")
    kind = str(payload.get("region_kind", "")).strip()
    if kind not in {"figure", "chart", "diagram", "photo", "table", "other"}:
        raise VisualRetrievalError("Visual result failed authorization validation")
    content = str(payload.get("content", "")).strip()
    if not content:
        content = f"{kind.capitalize()} on page {page_number}."
    return RetrievalCandidate(
        point_id=f"visual:{region_id}",
        document_id=document_id,
        document_version_id=version_id,
        generation_id=generation_id,
        document_title=str(payload.get("document_title", "Document")),
        page_number=page_number,
        content_type="image/png",
        content=content[:2000],
        chunk_index=0,
        score=score,
        evidence_kind=("image" if kind == "photo" else "figure" if kind == "other" else kind),
        region_id=region_id,
    )


def _match(field: str, value: UUID | str) -> models.FieldCondition:
    return models.FieldCondition(key=field, match=models.MatchValue(value=str(value)))
