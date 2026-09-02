# ADR 0024: Adaptive retrieval and fresh protected evidence

- Status: Accepted
- Date: 2026-09-02
- Accepted: 2026-09-02
- Milestone: 5.5

## Context

ADR 0023 introduced the ceiling-aware `phase5-quality-v2` contract, a protected
v3 benchmark, and the deterministic `hybrid-v2` candidate. One explicitly
authorized paid v3 attempt passed Recall@10, MRR@10, class, authorization,
identity, latency, and provider-call gates. Its validation nDCG@10 improved by
`4.1381%`, below the accepted `5%` requirement. The runner therefore withheld
holdout, product proof, promotion, and retry.

The observed v3 validation result is diagnostic evidence and cannot guide another
candidate. The still-sealed v3 holdout cannot be inspected or reused. Tuning-only
evidence, however, shows a viable deterministic composition of already accepted
components: preserve dense order for ordinary semantic queries and use balanced
dense/sparse RRF plus the pinned local reranker when query syntax carries an exact
or multi-intent signal. On the v3 tuning split this composition produced Recall@10
`0.9722`, nDCG@10 `0.8368` versus dense `0.7848` (`+6.62%`), MRR@10 `0.8449`, zero
identity violations, no added provider calls, and p95 latency within the accepted
bound.

A decision is required before freezing this candidate, creating new protected
evidence, or authorizing another paid attempt.

## Decision drivers

- Retain the accepted 5% relative nDCG@10 improvement requirement.
- Do not tune against a previously observed validation result or inspect a sealed
  holdout.
- Preserve dense semantic behavior while applying lexical and local-reranking work
  only where deterministic query syntax indicates it is useful.
- Keep routing explainable, provider-neutral, free at query time, and unable to use
  benchmark labels, expected answers, client authority, or retrieved content.
- Preserve authorization, citation identity, immutable generations, bounded
  candidate sets, deterministic fallbacks, and non-disclosing errors.
- Keep all prior candidates, fixtures, paid evidence, and release tags immutable.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Lower the nDCG threshold to the observed 4.14% | Would accept the current candidate | Moves the goal after validation and weakens the release claim |
| Tune `hybrid-v2` against the observed v3 validation result | May find a small adjustment quickly | Converts protected evidence into tuning data and invalidates the contract |
| Stop Phase 5 without another candidate | Avoids another paid attempt | Leaves the accepted hybrid-retrieval objective incomplete despite viable tuning evidence |
| Route ordinary queries to dense and exact/multi-intent queries to balanced hybrid plus local reranking | Preserves semantic ordering and retains lexical/multi-document gains using accepted components | Adds a versioned route and requires fresh protected evidence |
| Add a learned or LLM router | Could classify richer intent | Adds model, privacy, nondeterminism, operating, and paid-call boundaries |

## Decision

### 1. Keep the quality contract unchanged

Retain `phase5-quality-v2` exactly as accepted in ADR 0023. In particular, do not
lower or reinterpret the 5% relative nDCG@10 requirement. Recall, MRR, class floors,
authorization and citation identity, latency, and provider-call gates also remain
unchanged.

### 2. Freeze deterministic candidate `hybrid-v3`

Add evaluation-only profile `hybrid-v3` with selector revision
`hybrid-v3-selector-v1`:

- normalize query whitespace without changing case or Unicode;
- route an ordinary query to the existing `dense-v1` ranking path;
- route a query with an ADR 0023 exact signal or a frozen multi-intent keyword to
  balanced 1:1 RRF at `k=60`, deterministic multi-document diversification, and the
  pinned local reranker;
- recognize the multi-intent keywords `compare`, `contrast`, `combine`, `pair`,
  `versus`, `vs`, `both`, and `and` only at word boundaries; and
- default to the dense route when no signal matches.

The selector may inspect only query syntax. It cannot receive a benchmark class,
expected answer, relevance judgment, client-selected route, retrieved source
content, or model result. The profile fingerprint binds the selector rules, exact
and multi-intent patterns, fusion policy, 30/30/20/8 bounds, diversity policy, local
reranker name/revision/checksum, and normalization rule.

If sparse retrieval is unavailable or fails, return the already authorized dense
order. If local reranking is unavailable, malformed, or exceeds its timeout, return
the already authorized fused order. These fallbacks may reduce quality but cannot
expand scope or fail open on identity validation.

`dense-v1` remains the rollback profile. `hybrid-v1`, `hybrid-v2`, and
`hybrid-rerank-v1` remain unchanged. `hybrid-v3` is not the product default and is
not approved for promotion by this decision.

### 3. Create protected evaluation revision `phase5-retrieval-v4`

Reuse the synthetic v3 document corpus and v3 tuning judgments under new v4
identities; these are the only evidence used to select `hybrid-v3`. Create fresh
validation and holdout query text, judgments, and identifiers before any v4 paid
run. Freeze the same 120-chunk, 80-query, 60/20/20, class-balanced shape and retain
the `phase5-quality-v2` contract.

The fixture validator must prove that every v4 protected query is disjoint from all
v1-v3 validation and holdout query text and IDs. V1-v3 outcomes remain diagnostic,
and all previous holdouts remain sealed and ineligible for candidate tuning.

Validation executes once for the frozen v4 candidate. Holdout retrieval and output
remain physically withheld unless validation passes. A material candidate change
after v4 validation requires another ADR and fresh protected evidence.

### 4. Preserve paid-run and rollout approvals

Fixture generation, deterministic tests, model-artifact verification, and live
service checks must pass without paid provider use. Another paid benchmark requires
fresh explicit authorization after these free gates are complete. A paid failure is
not retried implicitly. Validation and holdout success still require a separately
approved end-to-end product proof, and aggregate evidence still requires user
acceptance before profile promotion.

## Consequences

- The quality standard remains stable rather than being adjusted to a near miss.
- Ordinary semantic queries retain dense ranking and avoid unnecessary sparse and
  reranker latency.
- Exact and multi-intent queries reuse pinned local components without a new paid
  provider call.
- A syntax rule such as `and` is intentionally simple and may over-route some
  queries; its behavior is explicit, fingerprinted, and covered by class gates.
- New protected judgments add maintenance and one future paid embedding batch, but
  restore a valid validation boundary.

## Acceptance resolution

The recommended direction was explicitly approved on 2026-09-02. The unchanged
quality bar, `hybrid-v3` contract, fresh `phase5-retrieval-v4` protected evidence,
free/local implementation, and separate future paid-run and promotion approvals are
accepted.

## Acceptance evidence required

- Golden selector tests cover every exact and multi-intent signal, ambiguous dense
  fallback, case/whitespace normalization, and a stable profile fingerprint.
- Product tests prove the dense route does not invoke sparse retrieval or reranking;
  the adaptive route reuses the identical trusted filter and revalidates every
  candidate identity; and sparse/reranker failures preserve safe fallback order.
- The v4 fixture is byte-reproducible, hashed, balanced, scope-valid, and has no
  protected query overlap with v3.
- The benchmark reports `hybrid-v3` and its fingerprint, writes no query or document
  content to results, and performs no holdout retrieval after a validation failure.
- All free deterministic, live integration, model-artifact, secret, and ignored-file
  checks pass before requesting a paid run.
- One separately authorized paid attempt passes validation, holdout, and product
  proof before any acceptance or promotion proposal.
