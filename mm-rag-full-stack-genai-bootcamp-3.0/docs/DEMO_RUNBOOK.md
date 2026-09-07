# Current MM-RAG demonstration runbook

This runbook presents the accepted durable/governed foundation and the closed
Phase 5 hybrid-retrieval implementation while keeping all release tags immutable.
PR #5 was squash-merged at `5436614`. Phase 6 ADRs 0025–0030 and Milestones
6.0–6.5 are implemented and accepted. The signed-in visual/table/calculation proof
passes, and `PHASE6_PROFILE=visual-table-v1` is the promoted default;
`PHASE6_PROFILE=disabled` remains the explicit rollback.
Phase 7 ADRs 0031–0036 are accepted and the evaluation/observability implementation
is available; final Phase 7 acceptance waits for its seven-day SLO baseline.

## Before the session

1. From the `3.0` directory, run `make setup` once. This provisions and verifies
   the pinned free BM25 and reranker artifacts outside request handling. Before a
   Phase 6 candidate proof, also run `make phase6-models` and
   `make phase6-models-verify`.
2. Confirm ignored `.env` and `.streamlit/secrets.toml` contain the local Auth0,
   PostgreSQL, Qdrant, SeaweedFS, RabbitMQ, and OpenAI settings. Never display them.
3. Run `make services`, `make observability`, `make migrate`, and `make runtime`.
4. In separate terminals run `make api` and `make ui`.
5. Run `make check-live`. This validates free dependencies and does not make paid
   OpenAI requests.
6. Open `http://localhost:8503`, sign in, and confirm the personal workspace,
   authenticated email, and Settings readiness.

Run `make check-acceptance PHASE5_EMBEDDING_COST_USD_PER_MILLION_TOKENS=<current-rate>`
only with explicit authorization. It makes paid OpenAI requests and is separate
from every free gate.

## Five-minute product story

1. **Architecture:** show the current workflow/DEV poster and explain PostgreSQL
   job truth, RabbitMQ wake-ups, immutable dense/sparse generations, and fenced promotion.
2. **Library:** upload a representative PDF, DOCX, image, Markdown, or text source.
   Point out the immediate durable job response and queued/running stage progress.
3. **Control:** demonstrate refresh and explain cooperative cancellation and immutable
   successor retry. Do not cancel the primary golden-path job.
4. **Ready state:** after promotion, show the READY document and authorized source download.
5. **Ask:** run semantic and exact-identifier questions, then inspect source/page evidence.
   Explain identical dense/sparse authorization filters, deterministic RRF, and dense fallback.
6. **Persistence:** refresh or sign out/in; reopen the job/document/conversation state.
7. **Operations:** show aggregate `make operations-status` output and explain the
   separate dispatcher/worker health, safe alerts, retention preview, and restore proof.
8. **Logout:** sign out and verify the protected workspace is no longer visible.

## Phase 7 operator proof

1. Run `make observability-status` and open the provisioned MM-RAG Grafana dashboards
   at `http://localhost:3003`.
2. Navigate the application, inspect a READY document, and ask a free/non-provider
   path where available. Confirm a single safe correlation crosses frontend, API,
   retrieval, and persistence without exposing content or credentials.
3. Submit structured feedback on an assistant answer. Optional comment and diagnostic
   metadata require separate consent; only an owner/admin can review the workspace queue.
4. Run `make phase7-evaluation` and verify the composed release summary passes with no
   provider calls and preserves validation-before-holdout ordering.
5. Run `make observability-baseline` once per representative day. Phase 7 cannot be
   accepted until seven distinct days span at least six elapsed days and ADR 0033
   records the reviewed numeric targets.

Detailed diagnosis, alert, and incident procedures are in
[`PHASE7_OBSERVABILITY_OPERATIONS.md`](PHASE7_OBSERVABILITY_OPERATIONS.md).

## Phase 6 accepted profile and rollback

The default configuration now enables `PHASE6_PROFILE=visual-table-v1`. Provision
and checksum-verify the pinned local models before starting the worker. To exercise
the accepted proof with a representative visual/table PDF:

1. Confirm the worker starts only with checksum-verified local Docling and CLIP trees.
2. Upload once and verify immutable promotion reports visual regions and validated tables.
3. Ask a visual relationship/table lookup and inspect the exact outlined page region.
4. Ask one supported exact calculation and inspect cited cells, ordered operands,
   unit/currency, rounding rule, and result.
5. Refresh and sign out/in; confirm the evidence persists for the authorized user.
6. Verify another tenant, stale generation, tombstone, and corrupted artifact receive
   generic unavailable responses and no bytes.
7. Check desktop/narrow widths, light/dark themes, keyboard controls, zoom, and
   non-color-only highlighting.
8. Stop on any failure; set `PHASE6_PROFILE=disabled` and restart the API/worker to
   roll back Phase 6 while preserving the accepted text path.

Uploading/indexing or asking through the live model boundary may incur provider cost.
Obtain fresh explicit authorization before this proof; prior Phase 5 approvals do not apply.

## Failure-safe talking points

- The original is verified before the document/version/job/outbox commit and HTTP 202.
- Broker downtime delays dispatch but cannot erase a committed job.
- Duplicate delivery cannot create overlapping fenced attempts or duplicate visibility.
- Cancellation before promotion leaves the prior active generation unchanged.
- Three failed execution attempts produce an inspectable terminal state; broker retries
  do not consume that budget.
- Public status uses stable codes and correlation IDs without provider errors, keys,
  object paths, document content, or tokens.
- Every retrieval requires tenant, workspace, document/version, and active generation.
- Sparse or reranker failure cannot broaden scope; retrieval falls back to the already
  authorized dense or fused order.
- Models are pinned and checksum-verified before startup; request paths do not download them.

## Visual acceptance checklist

- Review Overview, Library, Ask, Activity, and Settings at desktop and narrow widths.
- Confirm Library renders pending, queued, running, retry-scheduled, succeeded, failed,
  and cancelled states without layout breakage.
- Confirm stage/unit progress, retry timing, cancel, and successor retry are understandable.
- Check light/dark contrast, keyboard focus, loading, empty, validation, conflict, and
  dependency-error states.
- Confirm the sidebar and Settings show authenticated identity and role, while no token,
  secret, database URL, raw UUID detail, internal exception, or private context appears.

## Current acceptance record

- Auth0 login, authenticated email, personal workspace, PostgreSQL/Qdrant readiness,
  and logout were previously verified at Phase 3 port `8503`.
- Deterministic async API, worker, dispatcher, generation, tenant, large-upload,
  operations, and retention tests pass.
- PostgreSQL migration `20260830_0008`, RabbitMQ live topology/confirm/manual-ack,
  SeaweedFS provider behavior, independent runtime health, and temporary database
  restore are verified.
- On 2026-08-30, one explicitly approved signed-in acceptance upload reached
  `succeeded` on attempt 1, promoted a READY generation, and remained ready after
  navigation. API readiness included PostgreSQL, Qdrant, and object storage.
- The single grounded question returned the expected fact with the uploaded document
  as its citation; the conversation, answer, and citation persisted after navigation.
  No authentication token or secret value was displayed or added to tracked files,
  and no second paid run was made.
- Initial Phase 5 free implementation evidence covered the hashed 50-query contract,
  immutable successor reindex, real-Qdrant filter parity, deterministic RRF,
  sparse/reranker fallback, pinned offline model checks, and healthy rebuilt runtime
  containers. The first paid candidate stopped at the quality gate because dense
  Recall@10 saturated the v1 corpus; no paid end-to-end proof or automatic retry ran.
- The approved 2026-09-02 v2 attempt also failed validation. Authorization identity
  and latency passed, but hybrid Recall@10 did not improve and ranking metrics
  regressed slightly. The runner withheld holdout and the product proof, wrote only
  ignored tune/validation results, removed its temporary collection, and did not retry.
- ADR 0023 free/local implementation is complete. The hashed 80-query v3 fixture,
  ceiling-aware/class gates, deterministic `hybrid-v2` fingerprint, and all 194 live
  tests pass without provider calls.
- The single approved 2026-09-02 v3 attempt embedded 2,516 tokens for an estimated
  `$0.00005032`. `hybrid-v2` passed Recall, MRR, class, identity, latency, and
  provider-call gates, but its 4.14% relative nDCG@10 improvement missed the 5%
  requirement. Validation therefore withheld holdout and product proof, removed the
  temporary collection, and wrote only ignored tune/validation rows. No retry or
  rollout is authorized; `hybrid-v1` remains default.
- ADR 0024 is accepted and its free/local remediation is implemented. The unchanged
  5% nDCG gate now evaluates fingerprinted `hybrid-v3`: ordinary syntax follows
  dense order, while exact or multi-intent syntax selects balanced RRF plus the
  pinned local reranker. The reproducible 80-query v4 fixture reuses only v3 tuning
  evidence and has fresh hash-bound validation/holdout queries and identities.
- The single approved 2026-09-02 v4 attempt used one 2,545-token embedding batch
  for an estimated `$0.00005090`. `hybrid-v3` passed Recall, MRR, class, identity,
  latency, and provider-call gates, but its 2.28% relative nDCG@10 gain missed the
  required 5%. Validation withheld holdout and the product proof, removed the
  temporary collection, and wrote only ignored tune/validation rows. No retry or
  rollout is authorized; `hybrid-v1` remains default.
- The user approved closing Phase 5 without promoting `hybrid-v3` or running another
  paid remediation cycle. This is an honest quality-gate outcome, not a RAG product
  failure: the implementation remains available, the earlier Phase 3 end-to-end
  product proof remains valid, and dense retrieval remains the rollback path.
- PR #5 passed its required checks and was squash-merged into `main` at `5436614`;
  the reviewed source tree and merged tree match, and no Phase 5 release tag exists.
- Phase 6 decision kickoff PR #6 was squash-merged at `95d18b3`. ADRs 0025–0030
  were accepted on 2026-09-03, authorizing implementation in milestone order.
- Milestones 6.0–6.5 are implemented behind `visual-table-v1`: immutable visual and
  table provenance, scoped CLIP retrieval, normalized table/cell storage, closed
  Decimal calculation, `evidence-v1`, integrity-checked artifact streaming, and the
  region/table/calculation viewer. The free synthetic candidate passes validation
  then holdout with zero provider calls. Local schema/RLS, model, Docling, lifecycle,
  and citation-negative checks pass.
- On 2026-09-07, the signed-in application-shell check passed: authenticated email
  and Owner role, Personal workspace, one READY document, its persisted grounded
  conversation/citation, aggregate Settings readiness, direct PostgreSQL/Qdrant/
  object-storage API readiness, and logout protection were verified. No token or
  secret was displayed or persisted.
- The `visual-table-v1` representative visual/table/calculation proof passes and the
  profile is accepted and promoted. Its exact evidence and fail-closed behavior are
  recorded in the project plan and architecture handbook. PR #7 was squash-merged
  at `0eb0d16`; annotated tag `mm-rag-v6.0.0` marks verified closure commit
  `d97e8e8`.
