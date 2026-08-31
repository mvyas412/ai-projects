# Multimodal RAG architecture posters

> Rendered visual companions to the canonical [architecture handbook](ARCHITECTURE.md).
> The handbook remains the editable source of truth; regenerate these posters
> whenever architecture, data flow, technology, or phase status changes.

## Current Phase 3 workflow and DEV architecture

This Milestone 3.2 checkpoint distinguishes verified behavior—including the S3
adapter, SeaweedFS provider, and transactional outbox—from accepted-but-pending
Phase 3 components.

![MM-RAG current workflow and DEV architecture](current/mm-rag-current-workflow-dev-architecture.svg)

## Final production architecture

This is the target production system without phase or roadmap labels.

![Multimodal RAG final production architecture](images/10-final-production-architecture.png)

## Complete system and evolution roadmap

![Complete Multimodal RAG architecture and evolution roadmap](images/00-complete-production-architecture.png)

## Phase 1 — Working prototype

![Phase 1 working multimodal RAG prototype](images/01-phase-1-prototype.png)

## Phase 2 — Secure product foundation

![Phase 2 secure product foundation](images/02-phase-2-product-foundation.png)

## Phase 3 — Durable asynchronous ingestion

![Phase 3 durable asynchronous ingestion](images/03-phase-3-async-ingestion.png)

## Phase 4 — Fine-grained authorization and governance

![Phase 4 fine-grained authorization and governance](images/04-phase-4-governance.png)

## Phase 5 — Hybrid retrieval, fusion, and reranking

![Phase 5 hybrid retrieval, fusion, and reranking](images/05-phase-5-hybrid-retrieval.png)

## Phase 6 — Visual and table intelligence

![Phase 6 visual and table intelligence](images/06-phase-6-visual-table-intelligence.png)

## Phase 7 — Evaluation and observability

![Phase 7 evaluation and observability](images/07-phase-7-evaluation-observability.png)

## Phase 8 — Scalable production platform

![Phase 8 scalable production platform](images/08-phase-8-scalable-platform.png)

## Phase 9 — Enterprise integrations and commercial controls

![Phase 9 enterprise integrations and commercial controls](images/09-phase-9-enterprise-controls.png)

## Maintenance rule

1. Update `ARCHITECTURE.md` first.
2. Regenerate the affected poster using the shared visual specification in
   [`images/README.md`](images/README.md).
3. Verify technical labels and flows against the handbook.
4. Replace the existing image while preserving its stable filename.
