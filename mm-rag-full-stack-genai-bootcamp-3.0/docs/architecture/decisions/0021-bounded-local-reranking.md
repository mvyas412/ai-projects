# ADR 0021: Bounded local cross-encoder reranking

- Status: Proposed
- Date: 2026-08-31
- Milestone: 5.4–5.5

## Context

Hybrid retrieval aims for recall, but the final evidence set needs precision. A
cross-encoder can score a query and candidate text together more accurately than a
bi-encoder, at higher per-candidate latency. Sending authorized source excerpts to a
new hosted reranker would also create a new privacy, cost, and availability boundary.

FastEmbed provides lightweight ONNX cross-encoders and lists the Apache-2.0
`Xenova/ms-marco-MiniLM-L-6-v2` model at approximately 0.08 GB.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| No reranker | Lowest latency and complexity | May leave imprecise fused ordering |
| Hosted reranking API | Strong managed models and minimal local runtime | Per-query cost, external content transfer, provider outage, and new data-processing terms |
| Local PyTorch/SentenceTransformers cross-encoder | Broad model choice | Large runtime and image footprint for the first revision |
| Local FastEmbed ONNX cross-encoder | Free, compact, no source text leaves the deployment | Adds CPU/memory use, model artifact lifecycle, and timeout behavior |
| Qdrant late-interaction/ColBERT vectors | Efficient provider-side second stage | Adds another indexed representation and more ingestion/storage complexity |

## Proposed decision

Define a provider-neutral reranker protocol and evaluate a local FastEmbed ONNX
implementation using `Xenova/ms-marco-MiniLM-L-6-v2`. Rerank at most the top 20
authorized fused candidates and return at most eight evidence items. Bound candidate
text before inference and preserve original source/page/chunk identity separately
from model input.

The reranker is disabled by default until ADR 0018 validation proves benefit. Pin
the library, model revision, license, artifact checksum, input normalization, maximum
candidate count, maximum characters/tokens, timeout, and score-order semantics in the
retrieval profile. Load and health-check the model before serving traffic; never
download a model in the request path.

On timeout, resource pressure, malformed output, or model failure, use the already
authorized deterministic fused order. Revalidate every output identity and reject
duplicates or unknown candidates. A hosted reranker may be considered only through
a later privacy/cost ADR and must never receive content implicitly.

Official references:

- <https://qdrant.github.io/fastembed/examples/Supported_Models/>
- <https://www.sbert.net/docs/cross_encoder/usage/usage.html>

## Consequences

- The recommended first reranker has no per-query fee and keeps excerpts local.
- CPU latency and memory become measurable operating concerns.
- Safe fallback preserves availability without broadening authorization.
- Text-only reranking does not solve Phase 6 image/table understanding.

## Approval questions

1. Approve local FastEmbed instead of a hosted reranking API?
2. Approve `Xenova/ms-marco-MiniLM-L-6-v2` as the first evaluated model?
3. Approve the 20-candidate input and eight-item output bounds?
4. Approve fused-order fallback on reranker failure or timeout?

## Acceptance evidence required

- The reranker improves validation/holdout nDCG without violating ADR 0018 latency.
- Model checksum/revision/license and resource limits are reproducible.
- Failure, timeout, duplicate, unknown-ID, and cross-tenant tests fail safely.
- No candidate content leaves the deployment and no runtime request downloads artifacts.
- Rollout can switch between dense, hybrid-without-rerank, and hybrid-with-rerank
  profiles without reauthorizing or changing citation identity.
