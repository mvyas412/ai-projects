# ADR 0019: Qdrant-native sparse BM25 retrieval

- Status: Accepted
- Date: 2026-08-31
- Accepted: 2026-09-01
- Milestone: 5.1–5.2

## Context

Dense retrieval handles semantic similarity but can miss exact identifiers, names,
numbers, and uncommon terms. Phase 5 needs lexical evidence while preserving the
accepted Qdrant point identity and mandatory tenant/workspace/document/version/
generation filter from ADR 0015.

The current free development service is Qdrant 1.19, which supports named sparse
vectors, hybrid queries, and tenant-scoped IDF statistics. Qdrant documents local
client-side inference through FastEmbed for self-hosted deployments.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| PostgreSQL full-text search | Already operated, transactional metadata, RLS available | Duplicates chunk text/search state, needs cross-store ranking, and adds a separate authorization implementation |
| OpenSearch BM25/hybrid search | Mature analyzers, search pipelines, and relevance tooling | Adds a substantial service, duplicate dense/index state, operations, and another tenant boundary |
| Qdrant full-text payload filters only | No new model or service | Filtering is not a ranked lexical retrieval leg |
| Qdrant named sparse vectors with local FastEmbed BM25 | Same point identity/filter, one existing free service, native IDF and hybrid support | Requires sparse generation, schema/backfill, model pinning, and benchmark evidence |
| Managed sparse/reranking API | Minimal local compute | Recurring cost, external content transmission, availability, and provider lock-in |

## Decision

Use a named Qdrant sparse vector, `sparse-bm25-v1`, on each new immutable chunk point
alongside its dense vector. Generate document and query vectors locally with the
Apache-2.0 `Qdrant/bm25` FastEmbed model; do not use Qdrant Cloud inference or another
paid provider in the initial profile.

Configure the sparse vector with the IDF modifier. Compute IDF over a trusted
workspace filter while applying the stricter authorized document/version/generation
filter to actual retrieval. Client input never supplies either filter.

Qdrant 1.19 can add a named sparse vector schema to the existing collection. Existing
promoted points remain immutable and are never patched in place. Reindex an existing
document only through an idempotent successor ingestion generation that writes new
dense-and-sparse points and promotes atomically after verification. Record sparse
model/tokenizer/schema revisions in the generation manifest and pipeline fingerprint.
Future ingestion writes dense and sparse vectors together before promotion.

Hybrid retrieval is enabled only for a generation whose verified manifest declares
the required sparse profile. Missing or failed sparse data falls back to the accepted
dense path. It never broadens scope, queries an older generation, or treats a sparse
score as authorization evidence.

Pin the FastEmbed dependency, model revision, tokenizer configuration, license, and
artifact checksum. Provision/cache artifacts outside the request path; runtime search
must not download code or models dynamically.

Official references:

- <https://qdrant.tech/documentation/search/text-search/hybrid-search/>
- <https://qdrant.tech/documentation/tutorials/multiple-partitions/>
- <https://qdrant.tech/documentation/manage-data/collections/>
- <https://qdrant.github.io/fastembed/examples/Supported_Models/>

## Consequences

- Sparse retrieval remains free and uses the current Qdrant security boundary.
- Ingestion and active generations gain a new versioned output dimension.
- Successor reindexing and partial sparse availability require explicit progress and rollback.
- PostgreSQL FTS and OpenSearch remain viable if the benchmark or scale disproves
  the recommendation.

## Approval questions

1. Approve Qdrant sparse vectors instead of PostgreSQL FTS or OpenSearch?
2. Approve local `Qdrant/bm25` FastEmbed inference and its Apache-2.0 model?
3. Approve trusted workspace-scoped IDF with stricter retrieval filtering?
4. Approve dense-only fallback when sparse data or inference is unavailable?

## Acceptance resolution

All four recommendations were explicitly approved on 2026-09-01. The free local
Qdrant BM25 sparse-vector profile, trusted IDF boundary, stricter authorized search
filter, immutable successor-generation reindexing, and dense-only fallback are
accepted.

## Acceptance evidence required

- Exact-term and identifier Recall@10 improves on the ADR 0018 validation set.
- Dense and sparse legs receive structurally identical trusted authorization scope.
- Returned payloads and citations are revalidated after every retrieval/fusion stage.
- Successor reindex is idempotent, resumable, generation-aware, leaves the prior
  generation unchanged, and never promotes partial output.
- Cross-tenant, missing-generation, stale-manifest, and sparse-failure tests pass
  against real Qdrant.
