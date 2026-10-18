# Multimodal RAG architecture posters

> Rendered visual companions to the canonical [architecture handbook](ARCHITECTURE.md).
> The handbook and current editable SVG/Mermaid diagrams are authoritative.
> Older PNG posters below are historical or target illustrations, not current permissions.

## Current retained demo architecture — October 18

Phase 11's qualified two-person learning acceptance is merged in PR #31 (`768a67f`).
The existing deployment remains available for inspection of READY documents and
saved answers/citations. Worker stopped/restart-no; existing maintenance unchanged;
no new paid calls or resources. A stopped worker does not disable API chat: the
inspection restriction is operator-controlled, not a new runtime/UI interlock.

![Current retained inspection demo architecture](current/mm-rag-demo-architecture.svg)

## Phase 11 closure and demo lifecycle

Five-/ten-user validation and Next.js promotion remain deferred. Phase 5 closed
without quality acceptance. This is learning-project closure, not production certification.

![Limited Phase 11 acceptance and retained demo lifecycle](current/mm-rag-phase11-closure-demo.svg)

## Historical Phase 10 operational illustration

This view shows the implemented plan/authorize/evidence loops around the accepted
free-first learning deployment at its original illustration checkpoint. Its pending
labels predate accepted Phase 10 evidence; the handbook and current demo SVG above
supersede those status labels. Existing maintenance remains unchanged.

![Phase 10 operational hardening and recovery](images/10-phase-10-operational-hardening.png)

## Phase 7 workflow and DEV architecture reference

This historical developer-capability view shows the Phase 3/4 runtime and governance
boundaries, Phase 5 hybrid retrieval foundation, Phase 6 visual/table extraction,
and the Phase 7 evaluation and observability layer. Phase 6 remains released at
`mm-rag-v6.0.0`; Phase 7 is accepted with its seven-day baseline and pilot SLOs.
Its development ports, schema and retry labels are historical, not the current demo
runtime or permission to execute paid workflows. Its stable filename is preserved.

![Historical Phase 7 workflow and DEV architecture](current/mm-rag-current-workflow-dev-architecture.svg)

## Target production architecture — not a completion claim

This is an aspirational target system without phase or roadmap labels. It does not
claim the learning deployment implements every component or provides a production SLA.

![Multimodal RAG final production architecture](images/10-final-production-architecture.png)

## Historical system and evolution roadmap

This original roadmap is retained for design history. Use the current lifecycle
SVG and handbook for accepted, closed-without-acceptance and deferred phase status.

![Complete Multimodal RAG architecture and evolution roadmap](images/00-complete-production-architecture.png)

## Phase 1 — Working prototype

![Phase 1 working multimodal RAG prototype](images/01-phase-1-prototype.png)

## Phase 2 — Secure product foundation

![Phase 2 secure product foundation](images/02-phase-2-product-foundation.png)

## Phase 3 — Durable asynchronous ingestion

![Phase 3 durable asynchronous ingestion](images/03-phase-3-async-ingestion.png)

## Phase 4 — Fine-grained authorization and governance

The poster is the Phase 4 target-state companion. The editable
[Phase 4 policy matrix and threat model](PHASE4_POLICY_THREAT_MODEL.md) is implemented
through migration `20260831_0013`; Milestones 4.0–4.5 pass deterministic and free
live-service evidence and are accepted in PR #3's squash commit `57ee453`.

![Phase 4 fine-grained authorization and governance](images/04-phase-4-governance.png)

## Phase 5 — Hybrid retrieval, fusion, and reranking

Historical target: Phase 5 closed without quality acceptance. `hybrid-v1` remains
the default, `dense-v1` the rollback and `hybrid-v3` evaluation-only/unpromoted.

![Phase 5 hybrid retrieval, fusion, and reranking](images/05-phase-5-hybrid-retrieval.png)

## Phase 6 — Visual and table intelligence

This poster records the accepted and released Phase 6 visual/table architecture.

![Phase 6 visual and table intelligence](images/06-phase-6-visual-table-intelligence.png)

## Phase 7 — Evaluation and observability

![Phase 7 evaluation and observability](images/07-phase-7-evaluation-observability.png)

## Phase 8 — Scalable production platform

![Phase 8 scalable production platform](images/08-phase-8-scalable-platform.png)

## Phase 9 — Enterprise integrations and commercial controls

![Phase 9 enterprise integrations and commercial controls](images/09-phase-9-enterprise-controls.png)

## Phase 10 — Operational hardening and recovery

![Phase 10 operational hardening and recovery](images/10-phase-10-operational-hardening.png)

## Maintenance rule

1. Update `ARCHITECTURE.md` first.
2. Update the current editable Mermaid/SVG view and render it locally for review.
3. Verify technical labels, scope limits and flows against the handbook and ADRs.
4. Preserve clearly labeled historical/target PNGs and immutable release evidence.
   Paid image generation is not authorized for this update; the legacy visual
   specification remains in [`images/README.md`](images/README.md).
