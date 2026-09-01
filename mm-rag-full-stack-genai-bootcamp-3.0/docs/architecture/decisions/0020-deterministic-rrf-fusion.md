# ADR 0020: Deterministic reciprocal-rank fusion

- Status: Proposed
- Date: 2026-08-31
- Milestone: 5.3

## Context

Dense cosine scores and sparse BM25 scores are not directly comparable. A fixed raw
score blend can let one retrieval leg dominate because its scale differs by model and
query. Phase 5 needs a reproducible fusion contract with inspectable inputs and stable
tie-breaking.

Qdrant offers built-in RRF and distribution-based score fusion. The application can
also fuse separately retrieved authorized candidate lists itself.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Concatenate and sort raw scores | Small implementation | Mathematically invalid across score scales |
| Weighted normalized score fusion | Can outperform with careful tuning | Requires calibration and is sensitive to candidate score distributions |
| Qdrant-native RRF | One provider request and optimized execution | Provider-owned trace/tie semantics and less visibility into each leg |
| Application-owned RRF | Provider-neutral, deterministic, fully testable, and preserves leg ranks | Returns two bounded lists and adds application fusion work |

## Proposed decision

Retrieve at most 30 authorized candidates from each dense and sparse leg, then apply
application-owned reciprocal-rank fusion using stable point identity:

`score(point) = sum(weight_leg / (k + rank_leg))`

Start with `k=60` and equal leg weights. Tune only on the ADR 0018 tuning split;
freeze parameters before validation and holdout. Use zero ambiguity in rank numbering,
sort ties by stable point ID, and version the complete ranking profile.

Deduplicate by immutable Qdrant point/chunk identity. For multi-document scope,
recommend a maximum of three pre-rerank candidates per document; do not impose that
cap for a single-document scope. Preserve page/chunk provenance and return at most
20 candidates to an optional reranker and eight items to evidence assembly.

Both legs must receive the same trusted authorization filter and each returned payload
must pass ADR 0015 validation before fusion. Sparse-leg timeout or failure degrades to
the accepted dense order. Dense failure remains a non-disclosing dependency failure
in the first revision rather than silently switching product semantics. The fused
score never grants access or validates a citation.

Qdrant-native RRF may replace the application implementation only after parity,
traceability, authorization, latency, and rollback evidence under a superseding ADR.

Official reference:

- <https://qdrant.tech/documentation/search/hybrid-queries/>

## Consequences

- Results are reproducible across providers and easy to explain in evaluation output.
- Two candidate legs may cost more latency than one provider-native fused request.
- Diversification can reduce redundant context but must be evaluated for focused
  single-document questions.
- Parameters become versioned product behavior, not hidden constants.

## Approval questions

1. Approve application-owned RRF rather than Qdrant-native fusion?
2. Approve the initial `k=60`, equal weights, and 30-per-leg bounds?
3. Approve the multi-document diversity cap and final 20/8 candidate bounds?
4. Approve dense fallback for sparse failure and fail-closed behavior for dense failure?

## Acceptance evidence required

- Golden rank fixtures prove formula, deduplication, ties, and deterministic ordering.
- Validation/holdout metrics satisfy ADR 0018 without authorization or citation regression.
- Sparse timeout/error tests produce the documented dense fallback and safe telemetry.
- Candidate traces contain stable IDs, ranks, profile revision, and timings but no
  raw private content, secret, or provider coordinate.
