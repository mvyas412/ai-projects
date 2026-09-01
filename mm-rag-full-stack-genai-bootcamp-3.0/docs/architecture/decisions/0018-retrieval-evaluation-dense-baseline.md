# ADR 0018: Versioned retrieval evaluation and dense baseline

- Status: Proposed
- Date: 2026-08-31
- Milestone: 5.0

## Context

The accepted Phase 4 release uses authorized dense Qdrant retrieval with a final
limit of eight chunks. Phase 5 must not add sparse search, fusion, or reranking
because they sound better; it must prove that they improve retrieval on a stable
corpus without weakening authorization, citations, latency, or reproducibility.

The project has deterministic security tests and one accepted paid end-to-end proof,
but it does not yet have a versioned retrieval judgment set or a frozen dense-only
quality baseline.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Tune against a few demonstration questions | Fast and familiar | Overfits the demo and cannot detect broad regressions |
| Use only a public benchmark | Reproducible and large | Does not represent the product's document scopes, citations, OCR, or tenant rules |
| Use only private uploaded documents | Realistic | Cannot be committed, shared, or run safely in CI |
| Versioned public fixtures plus an ignored representative corpus | Reproducible contract plus realistic local evidence | Requires dataset governance, judgments, hashing, and separate result handling |
| LLM-as-judge as the required gate | Scores answers with little manual labeling | Nondeterministic, potentially paid, prompt-sensitive, and unsuitable as the sole release gate |

## Proposed decision

Create a repository-owned retrieval evaluation contract with two corpus tiers:

1. committed synthetic or redistributable fixtures with stable document, chunk,
   page, and generation identities; and
2. an optional ignored representative corpus and judgment file for realistic local
   acceptance. Private source text and raw results never enter Git.

The first benchmark should contain at least 50 judged queries, split 60/20/20 into
tuning, validation, and untouched holdout sets. Balance four query classes:

- semantic paraphrases;
- exact terms, identifiers, names, and numbers;
- multi-document ambiguity and source diversification; and
- unanswerable or unauthorized-scope negatives.

Each JSONL judgment records a dataset revision, query ID/text, query class, allowed
fixture scope, answerability, and graded relevant chunk/source identities. A canonical
manifest hashes every fixture and judgment file. Private equivalents use the same
schema but remain ignored.

### Dense baseline

Freeze the current dense-only profile before implementation: source commit,
pipeline fingerprint, corpus hash, chunking revision, embedding model identifier,
Qdrant collection schema, authorization-scope revision, retrieval limit, and metric
implementation revision. Required metrics are Recall@10, MRR@10, nDCG@10, source
coverage, empty-result correctness, authorization/citation validation, p50/p95
  retrieval latency, provider calls, estimated cost, and unanswerable-query
  false-positive behavior.

Required CI remains deterministic and free. A real OpenAI embedding or answer-quality
run is opt-in and requires explicit approval. Only aggregate, content-free results may
be committed from a private run.

### Recommended Phase 5 quality gate

On both validation and holdout sets, the accepted hybrid candidate should:

- improve Recall@10 by at least 10% relative and nDCG@10 by at least 5% relative;
- retain at least 98% of dense-baseline MRR@10;
- preserve 100% authorization and citation-identity validation;
- return no evidence for unauthorized negatives and not worsen the dense baseline's
  unanswerable-query false-positive rate;
- keep p95 retrieval latency within the greater of 1.5 times dense p95 or dense p95
  plus 200 ms; and
- add no per-query paid sparse or reranker provider call in the recommended local profile.

The holdout set is evaluated only for a release candidate, not during tuning.

## Consequences

- Retrieval changes become measurable and reversible.
- A small first dataset will not predict every production workload, so later phases
  must expand it using audited feedback.
- Private representative evidence remains useful without becoming repository data.
- Paid or nondeterministic evaluation cannot run implicitly.

## Approval questions

1. Approve the 50-query minimum and 60/20/20 split?
2. Approve the four recommended query classes?
3. Approve the quality and latency thresholds above?
4. Approve deterministic judgments as the release authority, with LLM judging only
   optional supplementary evidence?

## Acceptance evidence required

- Dataset/schema validation, stable hashing, duplicate detection, and split isolation pass.
- Dense baseline results are reproducible from a versioned manifest.
- Tenant, document, version, generation, and citation-negative tests remain mandatory.
- No private source text, raw model output, token, credential, or provider coordinate is tracked.
