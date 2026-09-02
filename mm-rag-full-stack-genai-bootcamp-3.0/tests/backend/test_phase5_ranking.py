import time
from uuid import UUID

import pytest

from backend.app.retrieval.ranking import (
    HYBRID_V2_DENSE_POLICY,
    HYBRID_V2_EXACT_POLICY,
    HYBRID_V2_TUNING_GRID,
    HYBRID_V3_DENSE_ROUTE,
    HYBRID_V3_HYBRID_RERANK_ROUTE,
    RankingInvariantError,
    RetrievalCandidate,
    diversify_candidates,
    hybrid_v2_profile_fingerprint,
    hybrid_v3_profile_fingerprint,
    reciprocal_rank_fusion,
    rerank_with_timeout,
    select_hybrid_v2_fusion,
    select_hybrid_v3_route,
)


def _candidate(point_id: str, document: int, score: float = 1.0) -> RetrievalCandidate:
    return RetrievalCandidate(
        point_id=point_id,
        document_id=UUID(int=document),
        document_version_id=UUID(int=document + 100),
        generation_id=UUID(int=document + 200),
        document_title=f"Document {document}",
        content_type="text/plain",
        content=f"Evidence {point_id}",
        page_number=1,
        chunk_index=document,
        score=score,
    )


def test_rrf_is_deterministic_deduplicated_and_score_scale_independent() -> None:
    dense = [_candidate("b", 1, 999), _candidate("a", 2, 100)]
    sparse = [_candidate("a", 2, 0.01), _candidate("c", 3, 0.001)]

    fused = reciprocal_rank_fusion(dense, sparse, k=60)

    assert [item.point_id for item in fused] == ["a", "b", "c"]
    assert fused[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert fused[1].score == pytest.approx(1 / 61)


def test_rrf_rejects_duplicate_or_conflicting_identity() -> None:
    duplicate = _candidate("a", 1)
    with pytest.raises(RankingInvariantError, match="duplicate"):
        reciprocal_rank_fusion([duplicate, duplicate], [], k=60)

    with pytest.raises(RankingInvariantError, match="disagreed"):
        reciprocal_rank_fusion([duplicate], [_candidate("a", 2)], k=60)


def test_weighted_rrf_preserves_dense_preference() -> None:
    dense = [_candidate("a", 1), _candidate("b", 2)]
    sparse = [_candidate("b", 2), _candidate("a", 1)]

    fused = reciprocal_rank_fusion(dense, sparse, k=60, dense_weight=2, sparse_weight=1)

    assert [candidate.point_id for candidate in fused] == ["a", "b"]


@pytest.mark.parametrize(
    "query",
    (
        'find "written notice"',
        "find ACME-774",
        "show version 2.4",
        "show SOC records",
        "find phishing-resistant access",
        "open handbook.pdf",
    ),
)
def test_hybrid_v2_exact_signals_select_balanced_fusion(query: str) -> None:
    assert select_hybrid_v2_fusion(query) == HYBRID_V2_EXACT_POLICY


def test_hybrid_v2_ambiguous_query_uses_frozen_dense_policy() -> None:
    assert select_hybrid_v2_fusion("how should administrators sign in") == HYBRID_V2_DENSE_POLICY
    assert {
        (policy.k, policy.dense_weight, policy.sparse_weight) for policy in HYBRID_V2_TUNING_GRID
    } == {
        (k, dense, sparse)
        for k in (20, 40, 60)
        for dense, sparse in ((1.0, 1.0), (2.0, 1.0), (3.0, 1.0), (1.0, 2.0))
    }
    assert (
        hybrid_v2_profile_fingerprint()
        == "91bc62b9ba956ff6e5e0561e8bf3728605c1fa4a8089c22327a86b80d7f3c74a"
    )


@pytest.mark.parametrize(
    "query",
    (
        'find "written notice"',
        "find ACME-774",
        "show version 2.4",
        "show SOC records",
        "find phishing-resistant access",
        "open handbook.pdf",
        "compare renewal periods",
        "CONTRAST retention rules",
        "combine both safeguards",
        "pair invoices versus budgets",
        "policy and notice requirements",
        "compare\n  renewal periods",
    ),
)
def test_hybrid_v3_signals_select_local_hybrid_rerank(query: str) -> None:
    assert select_hybrid_v3_route(query) == HYBRID_V3_HYBRID_RERANK_ROUTE


def test_hybrid_v3_ambiguous_query_stays_dense_and_fingerprint_is_frozen() -> None:
    assert select_hybrid_v3_route("how should administrators sign in") == HYBRID_V3_DENSE_ROUTE
    assert (
        hybrid_v3_profile_fingerprint()
        == "ed6930d3e84d50aefea6a5914af55a87c3f4bcc6f6bec54f49c7f8dfaebcdd9e"
    )


def test_multi_document_diversification_is_bounded_but_single_document_is_not() -> None:
    candidates = [
        _candidate("a", 1),
        _candidate("b", 1),
        _candidate("c", 1),
        _candidate("d", 2),
    ]

    diversified = diversify_candidates(candidates, document_count=2, max_per_document=2, limit=4)

    assert [item.point_id for item in diversified] == ["a", "b", "d"]
    assert (
        diversify_candidates(candidates, document_count=1, max_per_document=2, limit=4)
        == candidates
    )


class ReverseReranker:
    def scores(self, query, candidates):
        return tuple(float(index) for index, _ in enumerate(candidates))


class SlowReranker:
    def scores(self, query, candidates):
        time.sleep(0.02)
        return tuple(1.0 for _ in candidates)


def test_reranker_is_bounded_by_identity_and_falls_back_on_timeout() -> None:
    candidates = [_candidate("a", 1), _candidate("b", 2)]

    reranked = rerank_with_timeout(ReverseReranker(), "query", candidates, timeout_seconds=1)
    fallback = rerank_with_timeout(SlowReranker(), "query", candidates, timeout_seconds=0.001)

    assert [item.point_id for item in reranked] == ["b", "a"]
    assert fallback == candidates
