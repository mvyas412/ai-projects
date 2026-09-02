# ADR 0023: Ceiling-aware retrieval quality and deterministic candidate selection

- Status: Proposed
- Date: 2026-09-02
- Milestone: 5.5

## Context

The accepted Phase 5 implementation combines authorized dense and sparse retrieval
through deterministic equal-weight reciprocal-rank fusion (RRF). The first paid
candidate saturated the small v1 validation corpus. ADR 0022 therefore introduced a
larger v2 confounder corpus while retaining the ADR 0018 quality thresholds.

The single approved v2 attempt also failed validation. Dense and `hybrid-v1`
Recall@10 were both `0.9375`; nDCG@10 was `0.8585` and `0.8572`; and MRR@10 was
`0.8750` and `0.8542`. Authorization identity and latency passed. The runner
correctly withheld holdout and the end-to-end product proof.

The Recall@10 result exposes a bounded-metric problem: a 10% relative improvement
over `0.9375` requires `1.03125`, but recall cannot exceed `1.0`. Tuning-only class
aggregates expose a separate candidate problem. Equal-weight fusion improved
multi-document Recall@10 from `0.8571` to `1.0000`, matched exact-identifier recall,
but lowered semantic-paraphrase Recall@10 from `1.0000` to `0.6250`. Reranking
improved some ordering metrics but cannot recover relevant candidates removed before
the rerank stage.

The v2 validation result is now diagnostic evidence. It must not become an informal
tuning set, and the still-unevaluated v2 holdout must remain sealed. A new decision is
required before changing the benchmark, ranking profile, or paid-run boundary.

## Decision drivers

- Keep the quality claim measurable when a bounded baseline is near `1.0`.
- Preserve an actual improvement requirement rather than merely clamping an
  impossible target to the metric ceiling.
- Prevent aggregate gains from hiding a semantic, exact-term, or multi-document
  regression.
- Tune only against declared tuning evidence and protect validation and holdout.
- Keep ranking deterministic, provider-neutral, free in normal operation, and fully
  subordinate to the existing authorization boundary.
- Preserve `dense-v1`, `hybrid-v1`, and all accepted release history unchanged.

## Alternatives considered

### Quality-gate alternatives

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Keep the original gate and only make the corpus harder | Preserves the literal ADR 0018 threshold | Can saturate again, makes corpus difficulty carry the metric semantics, and requires repeated paid baselines |
| Clamp an impossible target to `1.0` | Simple | A perfect candidate may pass without demonstrating the intended relative gain, and the rule changes abruptly at the ceiling |
| Replace Recall@10 with Recall@5 | Creates more rank sensitivity | Changes the retrieval objective and can penalize useful evidence that remains inside the product's evidence depth |
| Require a reduction in remaining recall error near the ceiling | Bounded, monotonic, and still requires improvement | Changes the accepted formula and needs clear versioning and tests |

### Candidate-selection alternatives

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Keep equal-weight RRF | No runtime change | The v2 tuning evidence shows a material semantic recall regression |
| Use one globally dense-heavy RRF profile | Smallest change and likely protects semantic recall | May give up lexical and multi-document gains on queries that need them |
| Use deterministic query/scope signals to select between a small set of RRF profiles | Can preserve semantic evidence while retaining exact-term and diversified retrieval | Adds versioned routing rules and more regression cases |
| Use a learned or LLM query router | Can model richer intent | Adds training data, nondeterminism or provider cost, privacy review, and another failure boundary |
| Promote the current reranker as the primary fix | Improves final ordering in some cases | Cannot restore candidates lost before reranking and did not pass tuning evidence |

## Proposed decision

### 1. Version the quality formula

Create quality-contract revision `phase5-quality-v2`. Keep the original ADR 0018
Recall@10 rule whenever its target is feasible:

`candidate_recall >= dense_recall * 1.10`

When the dense baseline is greater than `10 / 11` and that target would exceed
`1.0`, require at least a 10% reduction in the remaining recall error instead:

`candidate_recall >= dense_recall + 0.10 * (1.0 - dense_recall)`

Use unrounded metric values for the comparison. Unless dense Recall@10 is already
`1.0`, the candidate must be strictly better than dense. At the observed v2 baseline
of `0.9375`, the ceiling-aware threshold is `0.94375`; with the current judgment
granularity, that requires recovering the missed relevant evidence rather than
passing on equality.

Keep the remaining ADR 0018 aggregate gates unchanged:

- nDCG@10 improves by at least 5% relative;
- MRR@10 retains at least 98% of the dense baseline;
- authorization/citation identity counts remain zero;
- the existing p95 latency bound remains in force; and
- hybrid retrieval adds no per-query paid provider call.

Add class guardrails on semantic-paraphrase, exact-term/identifier, and
multi-document answerable queries. For each class, candidate Recall@10 must not
regress and candidate nDCG@10/MRR@10 must each retain at least 98% of dense. At least
one of the exact-term or multi-document classes must improve Recall@10, nDCG@10, or
source coverage. Unauthorized-scope safety and answer-level abstention remain the
separate ADR 0022 contracts.

### 2. Create a protected v3 evaluation revision

Retain v1 and v2 as immutable diagnostic history. Do not evaluate, inspect, tune
against, or repurpose the v2 holdout.

Create a hashed `phase5-retrieval-v3` revision with at least 120 candidate chunks and
80 queries in a frozen 60/20/20 split. Validation and holdout must each contain at
least four semantic, four exact-term/identifier, and four multi-document answerable
queries, plus both unanswerable and unauthorized-scope negatives. The document
fixtures may be reused only if the protected query text, judgments, and identifiers
are fresh and the manifest is frozen before candidate tuning begins.

Tune only on the v3 tuning split. Validation runs once for a frozen candidate. A
validation failure emits no holdout metrics/output and makes that candidate revision
diagnostic; a materially changed candidate needs a newly versioned protected
validation contract before another release claim. Holdout runs once, only after
validation passes.

### 3. Evaluate a deterministic `hybrid-v2` candidate

Do not mutate `hybrid-v1`. Add an evaluation-only `hybrid-v2` profile that always
constructs dense and sparse candidates with the same trusted authorization filter,
then selects a fusion profile using only versioned query syntax and authorized scope
metadata:

- the default path uses dense-favoring RRF;
- exact-signal queries may use balanced or sparse-favoring RRF; and
- multi-document scopes retain the accepted deterministic diversity cap.

Exact signals may include quoted spans, mixed alphanumeric identifiers, version/date/
number patterns, acronyms, and file/domain-like tokens. The selector must never use a
benchmark class label, expected answer, client-supplied routing authority, model call,
or source content outside the already authorized retrieval boundary. Ambiguous input
uses the dense-favoring path.

Predeclare a small tuning grid before evaluating v3: RRF `k` in `{20, 40, 60}` and
dense:sparse weight ratios in `{1:1, 2:1, 3:1, 1:2}`. Select the simplest passing
configuration using only the tuning split, then freeze its rules, weights, model and
tokenizer revisions, candidate bounds, diversity policy, and code fingerprint.
Preserve the accepted 30 candidates per leg, 20 pre-rerank candidates, and eight
final evidence items unless a later ADR explicitly changes them.

`dense-v1` remains the safe rollback. `hybrid-v1` remains unchanged while the new
candidate is evaluated. `hybrid-rerank-v1` stays opt-in; reranking can be considered
for promotion only if it independently passes the same aggregate and class gates.

### 4. Preserve the paid and rollout boundaries

All fixture generation, selector tuning, regression tests, live-service checks, and
model-artifact verification must pass without a paid provider call. After the v3
dataset and candidate are frozen, obtain fresh explicit approval for one paid run.
The runner evaluates validation first, then holdout, then the end-to-end product
proof only if each preceding gate passes. A failed paid attempt is never retried
implicitly.

No candidate becomes the default release profile until the user accepts the aggregate
evidence. No change in this ADR may weaken backend authorization, returned-point
validation, citation identity, immutable generations, or non-disclosing errors.

## Consequences

- The recall rule remains meaningful near its mathematical ceiling while preserving
  the original rule where it is feasible.
- Class guardrails make the observed semantic loss visible instead of allowing an
  aggregate score to hide it.
- A deterministic selector adds explainable product behavior without a new model,
  provider, privacy boundary, or per-query charge.
- A larger fresh protected split adds fixture and judgment maintenance, but prevents
  tuning against already-observed validation evidence.
- Phase 5 remains implemented but unaccepted until the new contract, candidate, and
  one explicitly approved paid release proof pass.

## Approval questions

1. Approve the ceiling-aware Recall@10 formula while keeping the nDCG, MRR, latency,
   authorization, citation, and provider-call gates unchanged?
2. Approve the per-class non-regression guardrails and the fresh 80-query v3
   evaluation revision, while leaving the v2 holdout sealed?
3. Approve an evaluation-only deterministic `hybrid-v2` selector, the bounded tuning
   grid, and unchanged 30/20/8 candidate limits?
4. Approve keeping reranking opt-in and requiring new explicit authorization only
   after every free v3 and candidate check passes?

## Acceptance evidence required

- Formula boundary tests cover dense Recall@10 below, at, and above `10 / 11`, plus
  `1.0`, without rounded comparisons.
- The v3 manifest, minimum class counts, hashes, uniqueness, candidate pools, and
  split isolation pass deterministically.
- The selector has golden tests for every signal, ambiguous fallback, stable profile
  fingerprints, and no access to judgment labels or client-selected ranking authority.
- Dense and sparse legs preserve identical trusted scope and reject every unknown,
  excluded, duplicate, stale-generation, or cross-tenant identity.
- Tune-only evidence freezes one candidate before validation. Validation failure
  produces no holdout retrieval, metrics, or output.
- A newly authorized paid candidate passes validation and holdout under the same
  frozen profile before the end-to-end product proof and any rollout decision.
