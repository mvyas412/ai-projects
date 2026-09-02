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

Phase 5 implementation is active on `codex/phase5-hybrid-retrieval`. ADRs 0018–0021
are accepted, and the versioned benchmark, immutable sparse indexing, authorized
dense/BM25 retrieval, deterministic RRF, optional local reranking, rollout profiles,
and free regression gates are implemented. Final acceptance still requires one
successful, separately approved paid benchmark/end-to-end run; no paid call runs
implicitly. The first paid candidate on 2026-09-01 stopped at the quality gate
because the v1 corpus saturated dense Recall@10. ADR 0022's 120-chunk v2 benchmark,
validation-before-holdout execution, and separated identity/abstention metrics are
now implemented and pass all free gates without weakening the approved thresholds.
A newly approved paid v2 proof remains required.

See the latest application's tracked project plan and architecture handbook for
scope and status. Secrets, local context, environments, and generated data remain
outside Git.
