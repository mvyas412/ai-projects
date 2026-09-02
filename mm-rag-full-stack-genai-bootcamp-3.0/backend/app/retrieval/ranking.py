from __future__ import annotations

import hashlib
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Protocol, Sequence
from uuid import UUID

from fastembed.rerank.cross_encoder import TextCrossEncoder

from backend.app.retrieval.artifacts import RERANK_MODEL, resolve_local_model


class RankingInvariantError(RuntimeError):
    """Raised when a provider returns candidates that violate ranking identity."""


@dataclass(frozen=True, slots=True)
class FusionPolicy:
    revision: str
    k: int
    dense_weight: float
    sparse_weight: float


HYBRID_V2_DENSE_POLICY = FusionPolicy("hybrid-v2-dense-2-1-k60", 60, 2.0, 1.0)
HYBRID_V2_EXACT_POLICY = FusionPolicy("hybrid-v2-exact-1-1-k60", 60, 1.0, 1.0)
HYBRID_V2_PROFILE_REVISION = "hybrid-v2-selector-v1"
HYBRID_V2_DIVERSITY_POLICY_REVISION = "multi-document-max-three-v1"
HYBRID_V2_CANDIDATE_BOUNDS = (
    ("dense_candidates", 30),
    ("sparse_candidates", 30),
    ("pre_rerank_candidates", 20),
    ("final_evidence", 8),
)
HYBRID_V2_TUNING_GRID = tuple(
    FusionPolicy(f"hybrid-v2-grid-{dense:g}-{sparse:g}-k{k}", k, dense, sparse)
    for k in (20, 40, 60)
    for dense, sparse in ((1.0, 1.0), (2.0, 1.0), (3.0, 1.0), (1.0, 2.0))
)

_EXACT_SIGNAL_PATTERNS = (
    re.compile(r'["“][^"”]+["”]'),
    re.compile(r"\b(?=\S*[A-Za-z])(?=\S*\d)[A-Za-z0-9][A-Za-z0-9._/-]*\b"),
    re.compile(r"\b\d+(?:[.,]\d+)*(?:%|percent)?\b", re.IGNORECASE),
    re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)*\b"),
    re.compile(r"\b[A-Za-z]{3,}(?:-[A-Za-z]{2,})+\b"),
    re.compile(r"\b\S+\.(?:com|net|org|pdf|docx?|xlsx?|csv)\b", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    point_id: str
    document_id: UUID
    document_version_id: UUID
    generation_id: UUID
    document_title: str
    content_type: str
    content: str
    page_number: int | None
    chunk_index: int
    score: float

    @property
    def identity(self) -> tuple[UUID, UUID, UUID, str]:
        return (
            self.document_id,
            self.document_version_id,
            self.generation_id,
            self.point_id,
        )


class CandidateReranker(Protocol):
    def scores(self, query: str, candidates: Sequence[RetrievalCandidate]) -> tuple[float, ...]: ...


class FastEmbedCandidateReranker:
    def __init__(self, cache_dir: Path, *, threads: int = 2, max_characters: int = 4000) -> None:
        model_dir = resolve_local_model(RERANK_MODEL, cache_dir)
        self._max_characters = max_characters
        self._model = TextCrossEncoder(
            model_name=RERANK_MODEL.name,
            specific_model_path=str(model_dir),
            local_files_only=True,
            threads=threads,
        )

    def scores(self, query: str, candidates: Sequence[RetrievalCandidate]) -> tuple[float, ...]:
        documents = [candidate.content[: self._max_characters] for candidate in candidates]
        return tuple(float(value) for value in self._model.rerank(query, documents))


def select_hybrid_v2_fusion(query: str) -> FusionPolicy:
    """Select a frozen fusion policy from query syntax, never benchmark labels."""

    normalized = " ".join(query.split())
    if any(pattern.search(normalized) for pattern in _EXACT_SIGNAL_PATTERNS):
        return HYBRID_V2_EXACT_POLICY
    return HYBRID_V2_DENSE_POLICY


def hybrid_v2_profile_fingerprint() -> str:
    payload = {
        "profile_revision": HYBRID_V2_PROFILE_REVISION,
        "diversity_policy_revision": HYBRID_V2_DIVERSITY_POLICY_REVISION,
        "candidate_bounds": dict(HYBRID_V2_CANDIDATE_BOUNDS),
        "dense_policy": asdict(HYBRID_V2_DENSE_POLICY),
        "exact_policy": asdict(HYBRID_V2_EXACT_POLICY),
        "exact_patterns": [pattern.pattern for pattern in _EXACT_SIGNAL_PATTERNS],
        "normalization": "unicode-preserving-whitespace-collapse-v1",
        "tuning_grid": [asdict(policy) for policy in HYBRID_V2_TUNING_GRID],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def reciprocal_rank_fusion(
    dense: Sequence[RetrievalCandidate],
    sparse: Sequence[RetrievalCandidate],
    *,
    k: int,
    dense_weight: float = 1.0,
    sparse_weight: float = 1.0,
) -> list[RetrievalCandidate]:
    if k <= 0 or dense_weight <= 0 or sparse_weight <= 0:
        raise ValueError("RRF parameters must be positive")
    candidates: dict[str, RetrievalCandidate] = {}
    scores: dict[str, float] = {}
    for leg, weight in ((dense, dense_weight), (sparse, sparse_weight)):
        seen: set[str] = set()
        for rank, candidate in enumerate(leg, start=1):
            if candidate.point_id in seen:
                raise RankingInvariantError("A retrieval leg returned duplicate point identity")
            seen.add(candidate.point_id)
            existing = candidates.get(candidate.point_id)
            if existing is not None and existing.identity != candidate.identity:
                raise RankingInvariantError("Retrieval legs disagreed on candidate identity")
            candidates[candidate.point_id] = existing or candidate
            scores[candidate.point_id] = scores.get(candidate.point_id, 0.0) + weight / (k + rank)
    fused = [replace(candidate, score=scores[point_id]) for point_id, candidate in candidates.items()]
    return sorted(fused, key=lambda item: (-item.score, item.point_id))


def diversify_candidates(
    candidates: Sequence[RetrievalCandidate],
    *,
    document_count: int,
    max_per_document: int,
    limit: int,
) -> list[RetrievalCandidate]:
    if document_count <= 1:
        return list(candidates[:limit])
    selected: list[RetrievalCandidate] = []
    counts: dict[UUID, int] = {}
    for candidate in candidates:
        count = counts.get(candidate.document_id, 0)
        if count >= max_per_document:
            continue
        counts[candidate.document_id] = count + 1
        selected.append(candidate)
        if len(selected) == limit:
            break
    return selected


def rerank_with_timeout(
    reranker: CandidateReranker,
    query: str,
    candidates: Sequence[RetrievalCandidate],
    *,
    timeout_seconds: float,
) -> list[RetrievalCandidate]:
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="phase5-rerank")
    future = executor.submit(reranker.scores, query, candidates)
    original_rank = {candidate.point_id: rank for rank, candidate in enumerate(candidates)}
    try:
        scores = future.result(timeout=timeout_seconds)
        if len(scores) != len(candidates) or any(not math.isfinite(score) for score in scores):
            raise RankingInvariantError("Reranker returned malformed scores")
        scored = [replace(candidate, score=score) for candidate, score in zip(candidates, scores)]
        return sorted(
            scored,
            key=lambda item: (-item.score, original_rank[item.point_id], item.point_id),
        )
    except Exception:
        # Candidates were authorized before reranking, so their fused order is safe.
        future.cancel()
        return list(candidates)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
