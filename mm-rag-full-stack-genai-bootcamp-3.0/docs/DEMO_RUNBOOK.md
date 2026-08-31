# Phase 3 demonstration runbook

This runbook presents the durable asynchronous workflow while keeping the accepted
V1 and V2 releases immutable.

## Before the session

1. From the `3.0` directory, run `make setup` once.
2. Confirm ignored `.env` and `.streamlit/secrets.toml` contain the local Auth0,
   PostgreSQL, Qdrant, SeaweedFS, RabbitMQ, and OpenAI settings. Never display them.
3. Run `make services`, `make migrate`, and `make runtime`.
4. In separate terminals run `make api` and `make ui`.
5. Run `make check-live`. This validates free dependencies and does not make paid
   OpenAI requests.
6. Open `http://localhost:8503`, sign in, and confirm the personal workspace,
   authenticated email, and Settings readiness.

Run `make check-acceptance` only with explicit authorization: it makes paid OpenAI
requests and is separate from the normal Phase 3 release gate.

## Five-minute product story

1. **Architecture:** show the current workflow/DEV poster and explain PostgreSQL
   job truth, RabbitMQ wake-ups, immutable object/generation writes, and fenced promotion.
2. **Library:** upload a representative PDF, DOCX, image, Markdown, or text source.
   Point out the immediate durable job response and queued/running stage progress.
3. **Control:** demonstrate refresh and explain cooperative cancellation and immutable
   successor retry. Do not cancel the primary golden-path job.
4. **Ready state:** after promotion, show the READY document and authorized source download.
5. **Ask:** run a document- or collection-scoped question and inspect source/page evidence.
6. **Persistence:** refresh or sign out/in; reopen the job/document/conversation state.
7. **Operations:** show aggregate `make operations-status` output and explain the
   separate dispatcher/worker health, safe alerts, retention preview, and restore proof.
8. **Logout:** sign out and verify the protected workspace is no longer visible.

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
