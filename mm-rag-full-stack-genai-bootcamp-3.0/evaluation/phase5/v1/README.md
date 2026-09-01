# Phase 5 retrieval benchmark v1

This committed dataset contains synthetic, redistributable evidence only. It defines
24 stable chunks and 50 judged queries across semantic, exact-identifier,
multi-document, and negative classes with a frozen 60/20/20 split.
Answerable queries use the `@workspace` scope alias so all 12 fixture documents
compete during ranking. Negative judgments contain six genuinely unanswerable and
six unauthorized-scope cases; the latter identify relevant chunks that must remain
excluded by their narrower trusted scope.

Validate the contract without model or service calls:

```bash
uv run python -m scripts.run_phase5_evaluation
```

Score a complete result JSONL file with `query_id`, `ranked_chunk_ids`, `latency_ms`,
`provider_calls`, and `estimated_cost_usd` fields:

```bash
uv run python -m scripts.run_phase5_evaluation --results path/to/results.jsonl
```

After explicit paid-run approval, compare all three rollout profiles against live
Qdrant using one batched OpenAI embedding request:

```bash
uv run python -m scripts.run_phase5_benchmark \
  --allow-paid-openai \
  --embedding-cost-per-million-tokens <approved-current-rate>
```

Raw result identities are written below the ignored `evaluation/phase5/results/`
directory. The command exits unsuccessfully if the validation or holdout hybrid
gate does not satisfy ADR 0018.

Private representative documents, judgments, and raw results use the same schema but
remain ignored. Do not add customer material or raw provider output to this directory.
