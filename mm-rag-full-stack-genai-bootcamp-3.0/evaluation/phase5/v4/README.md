# Phase 5 retrieval evaluation v4

This frozen synthetic fixture evaluates the ADR 0024 `hybrid-v3` candidate under
the unchanged `phase5-quality-v2` contract.

- 120 chunks: 24 relevant-evidence chunks and 96 lexical/semantic confounders.
- 80 judged queries: 48 tuning, 16 validation, and 16 holdout.
- Each split covers semantic paraphrase, exact identifier, multi-document, and
  negative queries.
- The tuning split is the v3 tuning evidence under fresh v4 identities.
- Validation and holdout text, judgments, and IDs are fresh and hash-bound; the
  fixture validator rejects overlap with v3 protected queries.
- Holdout retrieval is not executed unless validation passes.

Regenerate with `uv run python -m scripts.build_phase5_v4_fixture` and verify with
`uv run python -m scripts.build_phase5_v4_fixture --check`. Benchmark result files
remain ignored because they may contain private operational evidence.
