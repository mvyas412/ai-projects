# ADR 0028: Visual embeddings, indexing, and modality-aware retrieval

- Status: Proposed
- Date: 2026-09-02
- Milestone: 6.2 and 6.4

## Context

Phase 5 stores text embeddings and sparse BM25 representations in one Qdrant
collection. Image evidence is searchable only through generated text. Phase 6 needs
text-to-image retrieval over figure/table crops while preserving the same trusted
workspace/document/version/generation boundary and safe fallback behavior.

Qdrant supports multiple vector representations and multivectors. Its documentation
notes that named vectors fit representations sharing one payload, while a separate
collection can be preferable when schemas and query patterns differ. FastEmbed's
[supported-model catalog](https://qdrant.github.io/fastembed/examples/Supported_Models/)
includes paired MIT-licensed CLIP text/vision encoders of modest size. SigLIP2 and
late-interaction ColPali/ColQwen-style retrieval are credible higher-cost candidates,
and Qdrant documents the storage and scaling implications of
[multivectors](https://qdrant.tech/documentation/manage-data/vectors/) and
[late interaction](https://qdrant.tech/documentation/tutorials-search-engineering/using-multivector-representations/).

## Decision drivers

- Add text-to-visual retrieval without changing the accepted text embedding profile.
- Keep local development and required CI free and CPU-capable.
- Reuse pinned FastEmbed/ONNX operations where quality permits.
- Prevent image-vector or route choice from becoming an authorization signal.
- Bound memory, candidate count, latency, and storage.
- Preserve deterministic fallback to the accepted text retrieval profile.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Caption/OCR text only | Reuses the current index and embedding API | Misses spatial/visual similarity and inherits caption errors |
| FastEmbed paired CLIP text/vision vectors | Free, local, CPU-friendly, existing dependency family, shared text-image space | Older model family and may be weak on dense charts or document layout |
| Local SigLIP2 dual encoder | Newer multilingual vision-language representation | Adds Transformers/PyTorch weight and needs careful preprocessing and hardware measurement |
| ColPali/ColQwen late-interaction multivectors | Strong document-page matching and fine-grained signals | High memory/storage/compute cost and more complex Qdrant operations |
| Managed multimodal embedding service | Low local model operations and potentially strong quality | Paid, network/privacy dependent, and provider-specific |

## Proposed decision

### Initial visual candidate

Evaluate pinned FastEmbed `Qdrant/clip-ViT-B-32-vision` with its paired text encoder
as `visual-clip-v1`. The official FastEmbed
[image-embedding example](https://qdrant.github.io/fastembed/examples/Image_Embedding/)
documents local image preprocessing and ONNX inference. The exact model revisions,
tree checksums, licenses, preprocessing, dimensions, and batch settings become part
of the Phase 6 pipeline fingerprint before implementation.

Treat SigLIP2 and late-interaction document models as measured successors, not
parallel first implementations. If `visual-clip-v1` fails the ADR 0025 gate, a new
decision must compare quality against memory, ingestion time, query latency, and
storage before adopting a heavier model. Hugging Face documents SigLIP2's paired
text/image embeddings and preprocessing in its
[official model guide](https://huggingface.co/docs/transformers/model_doc/siglip2).

### Qdrant boundary

Create one global, versioned visual-region collection rather than changing the
existing Phase 5 text-vector schema. Each visual point uses the ADR 0026 region ID
and mandatory tenant, workspace, document, version, generation, page, region-kind,
and vector-profile payload. The backend builds every filter from authorized
PostgreSQL state and revalidates every returned point before fusion or citation.

This is not a collection per tenant or document. It is one independently evolvable
visual schema whose active-generation visibility still comes from PostgreSQL.
Image crops remain in object storage; Qdrant stores vectors and bounded search
metadata only.

### Routing and fusion

Run the accepted text profile for every query. Add the visual leg only when a
versioned deterministic router detects visual intent such as figure, diagram,
image, chart, plot, axis, legend, or spatial-language signals. Table and calculation
intent is governed by ADR 0029. Client profile requests may narrow behavior for
testing but cannot broaden authorized scope or choose provider filters.

Fuse authorized text and visual candidates through application-owned deterministic
RRF using stable region/chunk identities. Bound each leg, deduplicate source regions,
preserve source diversity, and fingerprint route/fusion limits. A missing model,
timeout, malformed vector, or unavailable visual collection falls back to the
already authorized text result without exposing provider detail.

## Recommendation

Approve the separate visual collection and `visual-clip-v1` as the first free
candidate because they preserve the Phase 5 text index, fit the existing FastEmbed
operating model, and make rollback simple. Require the Phase 6 evaluation contract
to justify any SigLIP2, late-interaction, or managed-provider successor.

## Consequences

- Visual retrieval can evolve without rebuilding or mutating the accepted text collection.
- Cross-collection fusion and lifecycle reconciliation add application logic.
- CLIP is inexpensive to operate but may not meet chart/document-layout quality;
  failure triggers review rather than a lowered gate.
- Every new visual embedding revision requires successor generation output and
  measured storage/latency evidence.

## Approval questions

1. Approve the pinned FastEmbed CLIP pair as the initial free visual candidate?
2. Approve one global versioned visual collection separate from the text collection?
3. Approve deterministic visual-intent routing plus application-owned RRF and text fallback?
4. Approve a new ADR before adopting SigLIP2, late-interaction, or managed embeddings?

## Acceptance evidence required after approval

- Paired text/image embedding fixtures and exact artifact checksums reproduce offline.
- Visual search requires complete trusted scope and rejects every mismatched return.
- Route, bounds, RRF order, deduplication, and fallback are deterministic and fingerprinted.
- Cross-tenant, inactive-generation, tombstoned, and deleted visual results never surface.
- ADR 0025 validation reports quality, latency, peak memory, vector bytes, and model cost.
