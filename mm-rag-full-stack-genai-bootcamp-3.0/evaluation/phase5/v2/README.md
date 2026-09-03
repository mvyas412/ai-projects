# Phase 5 retrieval benchmark v2

This committed dataset is the accepted ADR 0022 remediation corpus. It contains
only synthetic, redistributable text: 120 stable chunks across 12 documents and
50 judged queries balanced across semantic paraphrase, exact identifier,
multi-document, and negative classes with a frozen 60/20/20 split.

Each document contains two evidence chunks and eight confounders. The confounders
include semantic near-neighbors, colliding identifiers and numbers, and
multi-document distractors. Every answerable quality query competes against at
least 50 authorized candidates. Six negative queries are genuinely unanswerable;
six use a narrower authorization scope and identify relevant chunks that must not
be returned.

Regenerate and verify the hashed fixture without model or service calls:

```bash
PYTHONPATH=. .venv/bin/python scripts/build_phase5_v2_fixture.py
PYTHONPATH=. .venv/bin/python scripts/build_phase5_v2_fixture.py --check
```

Validate the committed contract:

```bash
PYTHONPATH=. .venv/bin/python -m scripts.run_phase5_evaluation
```

The paid benchmark remains explicit opt-in. It evaluates tune and validation
first. If validation fails, it does not retrieve, score, or write holdout results.
Only a passing validation gate unlocks the holdout. Dense and hybrid remain the
release comparison; the reranker is diagnostic and disabled in the product.

Retrieval emptiness for unanswerable questions is reported only as a diagnostic.
The release gate separately requires zero unauthorized, explicitly excluded, or
unknown chunk identities. Grounded-answer abstention is tested at the answer
boundary and must contain no citations.

The v1 corpus remains unchanged as diagnostic history. Private representative
documents, judgments, provider output, and raw benchmark results remain ignored.
