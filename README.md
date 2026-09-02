# AI projects

This repository preserves versioned MM-RAG releases while future phase work is
planned in isolated branches and worktrees.

- `mm-rag-full-stack-genai-bootcamp-1.0/` — immutable V1 prototype,
  tagged `mm-rag-v1.0.0`.
- `mm-rag-full-stack-genai-bootcamp-2.0/` — accepted secure product foundation,
  tagged `mm-rag-v2.0.0`.
- `mm-rag-full-stack-genai-bootcamp-3.0/` — accepted durable asynchronous-ingestion
  release tagged `mm-rag-v3.0.0`, plus completed Phase 4 authorization, governance,
  audit, and lifecycle controls preserved at the annotated `mm-rag-v4.0.0` tag.

Phase 5 implementation is active on `codex/phase5-hybrid-retrieval`. ADRs 0018–0024
are accepted, and the versioned benchmark, immutable sparse indexing, authorized
dense/BM25 retrieval, deterministic RRF, bounded local reranking, adaptive
`hybrid-v3` candidate, rollout profiles, and free regression gates are implemented.
The single approved v4 attempt on 2026-09-02 passed Recall@10, MRR@10, class,
identity, latency, and provider-call gates, but its 2.28% relative nDCG@10 gain
missed the required 5%. The runner withheld holdout and the end-to-end proof as
designed. That approval is consumed, `hybrid-v1` remains the default, and Phase 5
remains open for an explicit close-or-remediate decision; no paid retry is authorized.

See the latest application's tracked project plan and architecture handbook for
scope and status. Secrets, local context, environments, and generated data remain
outside Git.
