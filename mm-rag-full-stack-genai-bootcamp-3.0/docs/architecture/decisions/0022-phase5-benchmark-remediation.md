# ADR 0022: Phase 5 benchmark remediation and negative-query contract

- Status: Proposed
- Date: 2026-09-01
- Milestone: 5.0 and 5.5

## Context

The first explicitly approved paid Phase 5 candidate run used the accepted ADR 0018
v1 corpus: 24 chunks and 50 queries evaluated at depth 10. The run was isolated,
used one batched `text-embedding-3-small` request, and stopped before the paid
end-to-end product proof when the quality gate failed.

Dense validation Recall@10 was already `1.0000`, so the required 10% relative
improvement was mathematically unattainable. Dense and hybrid validation nDCG@10
were `0.9507` and `0.9516`, which did not meet the required 5% relative improvement.
MRR, authorization identity, provider-call, and latency bounds passed. The local
reranker was not promotable because its tuning metrics regressed despite stronger
validation ordering.

All profiles reported zero unknown or out-of-scope candidates, but they also returned
allowed, irrelevant candidates for negative queries. The current
`negative_empty_accuracy` metric therefore conflates two different concerns:

1. authorization safety, which requires excluded or out-of-scope evidence never to
   appear; and
2. retrieval abstention, which requires a calibrated relevance threshold or an
   answer-level no-evidence decision.

The v1 result is useful diagnostic evidence but cannot prove the accepted relative
quality improvement.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Lower the approved relative thresholds | Makes the current result pass quickly | Converts an unattainable benchmark into a weaker release claim and hides corpus saturation |
| Clamp relative gates at the metric ceiling | Handles a perfect baseline mathematically | Still leaves the small corpus and weak discrimination unresolved |
| Change Recall@10 to a smaller depth | Creates more ranking sensitivity | Changes the accepted metric and may overemphasize first-position behavior |
| Version a harder corpus and retain the approved thresholds | Preserves the quality claim and makes lexical confounders measurable | Requires new fixtures, rotated holdout judgments, free validation, and one newly approved paid run |
| Add one global score threshold for empty negatives | Can force retrieval abstention | Dense, BM25, RRF, and reranker scores are not directly comparable; a weakly calibrated threshold can suppress valid evidence |
| Separate authorization negatives from answer-level abstention | Measures each invariant at its actual boundary | Requires clearer metrics and an answer-level negative acceptance case |

## Proposed decision

1. Preserve the ADR 0018 Recall@10, nDCG@10, MRR, latency, authorization, and
   provider-call thresholds. Do not lower or silently clamp them.
2. Retain v1 and its ignored raw results as diagnostic history, not Phase 5 release
   evidence.
3. Create a hashed `phase5-retrieval-v2` corpus with at least 120 chunks, including
   semantic near-neighbors, colliding identifiers/numbers, and multi-document
   distractors. Keep at least 50 balanced queries and the 60/20/20 split.
4. Rotate validation and holdout questions for v2. Tune only against the tuning split;
   evaluate holdout only after the frozen candidate passes validation.
5. Split negative evidence into explicit metrics:
   - unauthorized-scope safety requires zero excluded, out-of-scope, or unknown
     identities at every retrieval stage;
   - unanswerable behavior is measured at the grounded-answer boundary. Raw top-k
     retrieval emptiness remains descriptive until a separately calibrated,
     versioned confidence policy is approved.
6. Keep `hybrid-v1` as the implemented candidate and `dense-v1` as the rollback.
   Keep `hybrid-rerank-v1` disabled unless v2 tuning and validation prove benefit.
7. Add a deterministic preflight that rejects undersized candidate pools and prevents
   holdout evaluation/output when validation has not passed.
8. Require fresh explicit authorization immediately before one v2 paid benchmark
   and end-to-end product proof. The 2026-09-01 approval is consumed and cannot be
   reused.

## Consequences

- Phase 5 remains implemented but not accepted or release-ready.
- The approved quality claim stays meaningful rather than being adjusted to one run.
- A larger deterministic fixture adds maintenance cost but better represents hybrid
  retrieval's intended exact-term and ambiguity advantages.
- Authorization and abstention become independently testable and easier to explain.
- No model, provider, production profile, or paid-call behavior changes before this
  proposal is approved.

## Approval questions

1. Approve a v2 corpus with at least 120 chunks and rotated validation/holdout sets?
2. Approve preserving the original 10% Recall@10 and 5% nDCG@10 relative gates?
3. Approve separating unauthorized-scope identity safety from answer-level
   unanswerable abstention?
4. Approve keeping reranking disabled and requiring a fresh paid-run authorization
   only after all v2 free gates pass?

## Acceptance evidence required

- The v2 manifest, distribution, confounder, duplicate, scope, and split-isolation
  checks pass deterministically.
- No v1 holdout result or label is used to tune v2 ranking parameters.
- Validation is evaluated before holdout and a failed validation run emits no holdout
  metrics.
- Unauthorized negatives return zero excluded/out-of-scope/unknown identities.
- The grounded-answer negative case abstains without a citation.
- A newly authorized paid candidate satisfies ADR 0018 on v2 before Phase 5 is accepted.
