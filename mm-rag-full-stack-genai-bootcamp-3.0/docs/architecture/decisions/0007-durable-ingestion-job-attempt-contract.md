# ADR 0007: Durable ingestion job and attempt state contract

- Status: Accepted
- Date: 2026-08-30
- Milestone: 3.0

## Context

ADR 0004 gave document versions a small product-facing lifecycle for synchronous
Phase 2 indexing. That lifecycle cannot safely represent queue publication,
worker ownership, retries, expired work, cancellation, or attempt history. A
worker or API crash can currently leave a version in `processing`, and overwriting
one status row would erase the evidence needed to explain recovery.

Phase 3 needs a durable, provider-neutral contract before selecting a queue,
worker runtime, transactional-outbox boundary, or object-storage implementation.
PostgreSQL must remain the source of truth even when delivery is at least once and
messages arrive late, concurrently, or more than once.

## Decision drivers

- Preserve backend authorization and workspace scope for every job read or mutation.
- Recover safely after API, dispatcher, worker, PostgreSQL, Qdrant, or object-store failure.
- Make duplicate and out-of-order delivery harmless.
- Retain immutable attempt evidence without exposing secrets or raw provider errors.
- Support retries, backoff, heartbeats, cancellation, progress, and dead-letter diagnosis.
- Keep broker and worker implementation details outside the domain state machine.
- Preserve stable document/version identity and the accepted Phase 2 behavior.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Reuse `document_versions.status` only | Smallest schema and API change | Conflates content availability with execution; no attempt history, lease, retry schedule, or safe crash recovery |
| Add one mutable job row without attempts | Durable user-visible status with modest complexity | Repeated execution overwrites evidence; stale workers and retry ownership remain ambiguous |
| Durable job aggregate plus append-only attempts and fenced leases | Separates intent from execution, supports recovery and audit, remains provider-neutral | Requires more constraints, transition tests, a lease reaper, and explicit progress/error contracts |
| Make an external workflow engine authoritative | Rich timers, retries, and operational tooling | Premature operational dependency, provider coupling, and duplicated authorization/business state |

## Decision

Adopt a PostgreSQL job aggregate with append-only execution attempts and renewable,
fenced leases. PostgreSQL is authoritative for state and worker ownership; future
queue messages remain wake-up hints rather than job truth.

### Acceptance resolution on 2026-08-30

The review confirmed these parts of the contract:

- `queued` remains a canonical job state;
- members may cancel or retry jobs they requested, while owners/admins may do so
  for any job in their workspace, subject to the same fenced transition rules; and
- terminal jobs remain immutable, so manual recovery creates a successor job.

The review also accepted three total attempts, the first public progress shape
below, and projecting a document version back to `uploaded` when its first
indexing job is cancelled before any output promotion.

### Job identity and ownership

Each ingestion job has a stable UUID and carries `workspace_id`, `document_id`,
`document_version_id`, operation, pipeline fingerprint, requesting actor, creation
time, and optional predecessor job. Composite constraints must keep the job in the
same workspace as its document version. The backend derives workspace identity
from authenticated context; message fields and client input are never trusted as
authorization evidence.

The job is the durable record of requested work. A queue message is only a wake-up
hint containing the minimum identifiers needed to reload that record. PostgreSQL,
not the broker or worker process, answers status requests and decides whether work
may start or complete.

### Canonical job states

| State | Meaning |
| --- | --- |
| `pending` | The request and durable dispatch intent are committed; publication has not yet been acknowledged |
| `queued` | Dispatch has been acknowledged and the job is eligible for an execution attempt |
| `running` | Exactly one attempt owns a valid lease and may mutate attempt-scoped outputs |
| `retry_scheduled` | The previous attempt failed retryably and `next_attempt_at` has not arrived |
| `succeeded` | A validated output generation was promoted and the terminal audit mutation committed |
| `failed` | A permanent failure or exhausted retry budget ended the job |
| `cancelled` | Cancellation completed before output promotion |

Allowed transitions are:

```text
pending         -> queued | running | cancelled | failed
queued          -> running | cancelled | failed
running         -> succeeded | retry_scheduled | failed | cancelled
retry_scheduled -> queued | running | cancelled | failed
```

`pending -> running` and `retry_scheduled -> running` tolerate a worker receiving a
message before a publisher records its acknowledgement. Terminal states are
immutable. Automatic retries stay within the same job; a deliberate retry after a
terminal failure creates a new job linked by `predecessor_job_id` rather than
rewriting history.

Job transitions use compare-and-set semantics through a row revision or equivalent
database predicate. Timestamps record creation, first start, most recent transition,
and terminal completion. A cancellation request is recorded separately from state
so a running worker can observe it at safe checkpoints.

### Attempt and lease contract

An attempt row is created only when a worker atomically claims runnable work. Its
attempt number is monotonically increasing and unique within the job. Attempt
states are `running`, `succeeded`, `retryable_failure`, `permanent_failure`,
`cancelled`, and `lease_expired`; completed attempts are append-only.

The claim transaction must:

1. lock or conditionally update a non-terminal runnable job;
2. reject work before `next_attempt_at` or after cancellation was requested;
3. ensure no other unexpired attempt is active;
4. increment a monotonic fencing token;
5. create the attempt with worker identity, lease expiry, and heartbeat time; and
6. move the job to `running`.

Every heartbeat, progress update, retry decision, and completion supplies the job
ID, attempt ID, and fencing token. A stale or expired attempt cannot promote
outputs or change job state. Heartbeats renew the lease for bounded work. A
recovery process marks an expired attempt `lease_expired`, then either schedules
another attempt or terminates the job when its retry budget is exhausted.

### Retry, cancellation, and dead-letter semantics

- Failures are classified as retryable, permanent, cancelled, or lease-expired by
  stable application error codes rather than provider exception strings.
- Retry scheduling records `next_attempt_at`, the selected policy revision, and
  the attempt budget. The first-release policy is three total attempts
  (one initial attempt plus two automatic retries), with delays of approximately
  30 seconds and 2 minutes plus bounded jitter. Permanent input/validation failures
  and cancellations do not consume automatic retries.
- An authorized cancellation of `pending`, `queued`, or `retry_scheduled` work is
  immediate. Members may cancel/retry jobs they requested; owners/admins may do so
  for any job in their workspace; viewers remain read-only. Running work records
  `cancel_requested_at`; the worker stops at a safe checkpoint, and lease recovery
  completes cancellation if that worker dies. Authorization never bypasses lease,
  fencing, idempotency, or immutable-terminal-state checks.
- Successful promotion wins over a racing cancellation only when the fenced
  promotion transaction committed first. Terminal state is never reversed.
- `failed` with an exhausted budget is the durable product state. A broker dead-letter
  queue, if selected later, is operational evidence and never the source of job truth.

### Progress and safe errors

Progress is attempt-scoped and may restart when a retry begins. The first public
shape contains job `state`, stable `stage`, `attempt_number`, optional
`completed_units`, `total_units`, and `unit`, a server-derived percentage only when
a meaningful total exists, and `updated_at`. Stage codes begin with
`loading_original`, `extracting`, `chunking`, `embedding`, `writing_outputs`,
`validating`, and `promoting`; additions must remain backward compatible. Nested
worker/provider details are intentionally excluded from the first contract.

Public job errors contain a stable code, retryability classification, safe summary,
and correlation ID. Internal diagnostics stay in access-controlled logs/traces and
must exclude tokens, credentials, raw document content, and unfiltered dependency
responses.

### Relationship to document-version status

Job state and content availability remain separate:

- a first indexing job may project the version as `processing` until promotion;
- successful promotion projects the version as `ready`;
- terminal failure projects `failed` only when no prior active generation exists;
- cancellation before any first promotion projects the version back to `uploaded`,
  preserving the durable original for a later job;
  if an older active generation exists, the version remains `ready`; and
- reprocessing never hides an already active generation while replacement work runs.

ADR 0008 defines generation visibility and promotion. No queue or outbox state may
directly mark a document version ready.

## Consequences

- Job status survives process restarts and remains explainable across retries.
- Fencing prevents a slow or resurrected worker from committing after ownership moved.
- Append-only attempts improve auditability and failure diagnosis.
- Additional database constraints, recovery scheduling, clock discipline, and
  concurrency tests are required.
- Broker delivery guarantees can remain at least once because execution is claimed
  and completed against durable state.

## Deferred tuning

Lease duration, heartbeat interval, execution timeout, and any retry-policy revision
after the initial three-attempt profile require measurement against representative
documents. Those values must be documented before the worker-runtime ADR is accepted;
they do not change the durable state or fencing contract in this ADR.

## Acceptance evidence required

- Transition and database-constraint tests reject every illegal or cross-workspace mutation.
- Concurrency tests prove one active fenced attempt per job.
- Crash tests recover expired leases without allowing stale completion.
- Duplicate and out-of-order delivery tests do not create overlapping attempts.
- Cancellation/retry races have deterministic terminal outcomes.
- Status and error responses disclose no internal dependency details or secrets.
