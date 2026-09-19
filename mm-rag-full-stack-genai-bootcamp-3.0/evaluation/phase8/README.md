# Phase 8 release evidence

Store private run output under ignored `evaluation/phase8/results/`. The release gate
requires one passing JSON record for each scenario named by
`scripts.phase8_evidence.REQUIRED_SCENARIOS`. Every record uses schema
`mm-rag-phase8-evidence-v2` and records observations, never secrets, tokens, document
text, prompts, or user identities.

The bounded-load record includes ordered 1-, 3-, 5-, and 10-user stages with
`error_count` and measured `p50_ms`/`p95_ms` for each stage. The backup-restore
record includes measured `rpo_hours` and `rto_hours`; rollback includes
`data_integrity_verified: true`. Phase 7 must first freeze the latency/error SLO
threshold against which the measured values are reviewed.

Example structural record:

```json
{
  "schema": "mm-rag-phase8-evidence-v2",
  "scenario": "worker-restart",
  "outcome": "pass",
  "observed_at": "YYYY-MM-DDTHH:MM:SSZ",
  "notes": "Non-sensitive operator summary"
}
```
