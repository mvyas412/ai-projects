# ADR 0025: Phase 6 visual and table evaluation contract

- Status: Proposed
- Date: 2026-09-02
- Milestone: 6.0

## Context

The current product can extract PDF text, describe a standalone image, and index
page-aware text chunks. It does not preserve figure/table regions, evaluate native
visual retrieval, or prove exact numerical answers from structured tables. Phase 6
must establish a protected baseline before selecting extractors, vision models,
image embeddings, routing, or a calculation engine.

Phase 5 also demonstrated why a candidate must not be tuned against observed
validation results. Its v4 validation and holdout remain outside Phase 6 and must
not be reused as Phase 6 tuning evidence.

## Decision drivers

- Measure visual and table improvement against the current OCR/text/Markdown path.
- Cover retrieval, region identity, extraction quality, exact calculations, and
  end-user evidence inspection rather than a single aggregate score.
- Keep required CI deterministic and free.
- Prevent private documents, raw model output, and protected judgments from entering Git.
- Withhold holdout evidence until one frozen candidate passes validation.
- Preserve authorization and citation identity as hard gates, not quality metrics.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Tune against a few demonstration PDFs | Fast to assemble | Encourages demo overfitting and cannot support a release claim |
| Use only a public document benchmark | Reproducible and shareable | Usually omits workspace authorization, exact product citations, and UI evidence behavior |
| Use only private representative documents | Realistic | Cannot be shared in Git and makes CI evidence incomplete |
| Versioned redistributable fixtures plus an ignored representative tier | Reproducible required gate plus realistic local evidence | Requires dataset governance, hashing, adjudication, and strict result handling |
| Make an LLM judge the release authority | Reduces manual labeling | Nondeterministic, potentially paid, and vulnerable to prompt/model drift |

## Proposed decision

Adopt a two-tier `phase6-visual-table-v1` evaluation contract.

### Corpus and split

The required committed tier should contain at least 40 independently locatable
visual/table regions and 80 judged questions, frozen 60/20/20 into tune,
validation, and untouched holdout splits. Each protected split must represent:

1. figure/diagram object and relationship questions;
2. chart label, trend, comparison, and plotted-value questions;
3. table cell/header lookup questions;
4. supported numerical calculation questions; and
5. unanswerable, ambiguous, and unauthorized-scope negatives.

The corpus must include digitally generated and scanned examples, multi-page
documents, visually similar distractors, repeated labels, merged table cells,
units, footnotes, and cross-document ambiguity. Each judgment identifies the
authorized document/version, page, region, relevant cells when applicable,
answerability, calculation contract, and graded evidence identities.

An optional ignored representative tier uses the same schema. Source files,
judgments, raw identities, and model output in that tier remain outside Git.

### Baselines and measures

Freeze the current text/OCR/Markdown behavior before implementing Phase 6. Report:

- Recall@5 and Recall@10, MRR@10, nDCG@10, and source/region coverage by class;
- region identity, document/version/page, authorization, and citation validation;
- table detection, cell-text, row/column/header association, and type-validation measures;
- supported exact-calculation accuracy and safe-abstention accuracy;
- answer groundedness using deterministic expected facts and evidence identities;
- p50/p95 ingestion and retrieval latency, artifact bytes, model/provider calls,
  and estimated cost; and
- text-only regression against the retained Phase 5 default and dense rollback.

The proposed quality gate requires, on validation and later holdout:

- at least a 10% reduction in remaining Recall@10 error over the relevant
  OCR/Markdown baseline and at least 5% relative nDCG@10 improvement;
- no answerable class below its corresponding baseline;
- 100% authorization, returned-identity, and citation-region validation;
- 100% correctness for declared supported exact calculations and 100% abstention
  for ambiguous or unsupported calculations; and
- no more than 2% relative Recall@10 or MRR@10 regression for text-only questions.

Latency, storage, and paid-cost budgets must be measured during tuning and frozen
before validation. They cannot be relaxed after a protected result is observed.

### Execution and evidence handling

- Tune may run repeatedly; validation runs only for a fingerprinted candidate.
- Holdout retrieval, scoring, and output remain withheld until validation passes.
- A material candidate or metric change after validation requires a new ADR and
  fresh protected evidence.
- Required CI uses deterministic fixtures and local/fake providers only.
- Any real paid model or provider evaluation requires fresh explicit authorization.
- LLM judging may be supplementary but cannot override deterministic identity,
  calculation, authorization, or citation failures.

## Recommendation

Approve this contract before any Phase 6 implementation. It creates one release
authority for all later extractor/model choices and prevents the team from choosing
technology on attractive demos alone.

## Consequences

- Phase 6 begins with measurable evidence rather than implementation momentum.
- Building and adjudicating a balanced corpus is real work, but it reduces later
  rework and protects the release claim.
- Exact calculation is intentionally strict: an unsupported operation must abstain
  rather than return a plausible number.
- A local candidate can fail quality without invalidating the existing RAG product.

## Approval questions

1. Approve the two-tier corpus and 80-question minimum?
2. Approve the five balanced question classes and 60/20/20 split?
3. Approve the quality, identity, calculation, and text-regression gates?
4. Approve validation-before-holdout and explicit authorization for every paid run?

## Acceptance evidence required after approval

- Dataset schema, canonical hashes, duplicate detection, split isolation, and
  protected-overlap checks pass.
- The OCR/text/Markdown baseline is reproducible from a versioned manifest.
- A regression proves validation failure emits no holdout retrieval or output.
- Raw private content, protected result identities, tokens, credentials, and
  provider coordinates remain ignored.
