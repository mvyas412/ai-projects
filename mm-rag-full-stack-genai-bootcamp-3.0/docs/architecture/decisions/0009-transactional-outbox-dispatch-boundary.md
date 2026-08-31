# ADR 0009: Transactional outbox dispatch and recovery boundary

- Status: Accepted
- Date: 2026-08-30
- Milestone: 3.0

## Context

ADRs 0007 and 0008 make PostgreSQL authoritative for durable ingestion jobs,
attempt ownership, idempotency, and output visibility. Phase 3 still needs to send
wake-up messages to a queue without losing work or making a broker authoritative.

A PostgreSQL commit and a broker publish cannot normally share one atomic
transaction. Publishing after the database commit can lose a wake-up when the API
or dispatcher crashes in between. Publishing first can create a message for a job
whose database transaction later rolls back. Retrying either operation can also
produce duplicate messages.

The boundary must therefore make lost dispatch impossible, make duplicate dispatch
harmless, and remain independent of the queue/broker and worker-runtime choices in
ADRs 0010 and 0012.

## Decision drivers

- Commit the job and its dispatch intent atomically in PostgreSQL.
- Keep API latency independent of broker availability.
- Recover after API, dispatcher, network, or broker failure without manual data repair.
- Support at-least-once publication while preserving ADR 0007 fencing and ADR 0008 idempotency.
- Prevent queue payloads from becoming trusted authorization or job state.
- Make delayed retries, publication failures, and aging backlog observable.
- Keep payloads minimal, versioned, and free of secrets or document content.
- Avoid distributed transactions and broker-specific behavior in the domain model.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Publish directly inside the API request after committing the job | Simple control flow and immediate publication | A crash after commit but before publish strands the job; broker outages increase API latency and failures |
| Publish before committing PostgreSQL | Broker receives work quickly | A database rollback leaves a message for a nonexistent job; consumers must handle avoidable phantom work |
| Use a distributed transaction across PostgreSQL and the broker | Theoretical atomicity | Poor provider support, high operational complexity, coupling, and fragile recovery |
| Let workers poll `ingestion_jobs` directly | No broker publication gap | Couples scheduling and execution, creates hot polling/locking pressure, and weakens the independently scalable queue boundary |
| PostgreSQL transactional outbox with at-least-once publication | Atomic local commit, broker-independent API, recoverable delivery, and provider neutrality | Requires an outbox table, dispatcher leases, duplicate-safe consumers, retention, and operational monitoring |

## Decision

Adopt a PostgreSQL transactional outbox. Every transition that makes an ingestion
job eligible for execution writes one immutable dispatch event in the same database
transaction as the job mutation. A separate dispatcher leases due outbox rows,
publishes them to the future broker, and records acknowledged publication in a
later PostgreSQL transaction.

The queue message remains a wake-up hint. The consumer reloads the job from
PostgreSQL and must win the fenced claim from ADR 0007 before doing work. Delivery
is intentionally at least once; neither the outbox nor a future broker promises
exactly-once execution.

This decision selects the outbox pattern and relational boundary only. It does not
select a broker, dispatcher framework, worker runtime, cloud provider, or object store.

### Acceptance resolution on 2026-08-30

The review accepted the complete recommendation, including:

- at-least-once publication with duplicate-safe worker claims;
- indefinite publication retry with capped backoff and operational alerts;
- 30-day retention for published or discarded rows while pending rows are retained;
- strict per-job ordering without a global ordering guarantee;
- operational-only outbox inspection/replay, with user retry remaining a successor job; and
- deferring exact dispatcher lease and batch tuning to ADR 0012 while requiring
  bounded batches and expiring leases.

### Intake and initial dispatch boundary

The recommended upload sequence is:

1. Stream the original to the object-storage boundary and verify its size and SHA-256.
2. Open one PostgreSQL transaction.
3. Create or replay the immutable document version and idempotent ingestion job.
4. For a newly eligible job, insert dispatch sequence `1` in the outbox and append
   the safe audit event in that same transaction.
5. Commit PostgreSQL, then return the durable job response to the client.
6. Let the dispatcher publish independently of the API request.

If object storage succeeds but PostgreSQL rolls back, ADR 0008 orphan cleanup may
remove the unreferenced object later. If PostgreSQL commits, a durable outbox row
always exists even when every dispatcher or broker instance is unavailable.

The API must not publish directly as a second required success step and must not
return a successful asynchronous response before the original is verified and the
database transaction commits.

### Retry dispatch boundary

When an execution attempt fails retryably, the transaction that moves the job to
`retry_scheduled` also inserts the next outbox event with a monotonically increasing
`dispatch_sequence` and `available_at = next_attempt_at`. No independent scheduler
must reconstruct missing retry intent by scanning mutable job history.

Manual recovery creates a successor job under ADR 0007. Its initial dispatch is
sequence `1` for that new job; terminal predecessor rows are never reopened.

### Outbox record contract

The first schema should contain at least:

| Field | Purpose |
| --- | --- |
| `id` | Stable UUID reused for every publication attempt of this event |
| `workspace_id`, `job_id` | Tenant-constrained aggregate identity with a composite foreign key to the job |
| `dispatch_sequence` | Monotonic eligibility cycle within the job; unique with `job_id` |
| `event_type` | Stable code, initially `ingestion.job.available` |
| `schema_version` | Integer payload contract version, initially `1` |
| `payload` | Immutable minimal JSON generated by trusted backend code |
| `available_at` | Earliest publication time; also carries publication backoff |
| `publication_attempt_count` | Number of broker publication calls attempted |
| `lease_owner`, `lease_expires_at` | Recoverable dispatcher claim; never exposed publicly |
| `published_at` | Broker acknowledgement recorded by PostgreSQL |
| `discarded_at`, `discard_reason` | Safe terminal marker when the target job is already terminal before useful publication |
| `last_error_code`, `last_error_at` | Stable operational code and time, never a raw provider exception |
| `created_at`, `updated_at` | Database timestamps for age, lag, and retention |

The immutable broker payload should contain only:

```json
{
  "event_id": "uuid",
  "event_type": "ingestion.job.available",
  "schema_version": 1,
  "job_id": "uuid",
  "occurred_at": "server timestamp"
}
```

Workspace identity, document metadata, object keys, user claims, filenames,
content, prompts, credentials, and provider configuration stay out of the message.
The worker derives trusted workspace and resource scope by reloading `job_id` from
PostgreSQL. A broker message is never authorization evidence.

### Dispatcher claim and acknowledgement

The dispatcher should:

1. Select due, unpublished, undiscarded rows with a bounded batch and
   `FOR UPDATE SKIP LOCKED` or equivalent PostgreSQL semantics.
2. Set a short renewable lease and commit before calling the broker.
3. Publish outside the database transaction using the stable outbox event ID.
4. After an unambiguous durable broker acknowledgement, open a new transaction,
   verify lease ownership and that the row was not discarded, mark it published,
   and conditionally move a `pending` or due `retry_scheduled` job to `queued`.
5. Leave a job that is already `running` or terminal unchanged.

If acknowledgement is missing or ambiguous, the event remains unpublished. After
the lease expires, the same event ID is published again. A worker may receive the
message before `published_at` is recorded; ADR 0007 already permits
`pending -> running` and `retry_scheduled -> running` for this race.

### Publication retry and backpressure

Broker publication failures do not consume the job's three execution attempts.
They update only outbox delivery metadata and retry with exponential backoff plus
bounded jitter. The recommendation is approximately 1 second, 5 seconds,
30 seconds, and 2 minutes, then a 5-minute cap while retrying indefinitely.

There is no automatic terminal publication-failure state in the first release:
dropped dispatch is more dangerous than a visible aging backlog. Alert when an
event has at least 10 failed publication attempts or the oldest due unpublished
event is more than 15 minutes old. A broker outage must create backpressure and
operator visibility, not API data loss or a hot retry loop.

### Cancellation, duplicates, and ordering

- Cancellation may mark unpublished events discarded in the same transaction, but
  it does not require broker message deletion or revocation.
- A message already in flight may still arrive after cancellation; the worker
  reloads the terminal/cancel-requested job and performs no work.
- Publication retries reuse the same `event_id`. Optional broker deduplication is
  useful but is never required for correctness.
- Per-job order follows `dispatch_sequence`; no global ordering is required.
- Consumers must ignore unknown schema versions safely and surface an operational
  error without logging the raw payload.
- A broker dead-letter queue is operational evidence only. PostgreSQL job state and
  outbox state remain authoritative.

### Authorization and visibility

Outbox rows are internal infrastructure records. They are not returned by the
public job API and are not directly replayed by members, owners, or admins. User
retry remains the authorized successor-job operation defined in ADRs 0007–0008.

Operational tooling may inspect safe event IDs, job IDs, age, attempt counts, and
stable error codes under least privilege. It must not expose raw provider errors,
secrets, object keys, document content, or untrusted message bodies.

### Retention and operational recovery

Pending events are never removed by retention. Published or discarded events may
be deleted only after a documented retention window and only after their job state
is durable. The initial recommendation is 30 days, with immutable audit events and
job/attempt history retained under their separate policies.

Operational replay republishes the same unpublished event ID. It must not create a
new job attempt or mutate a terminal job. Repair of malformed internal payloads
requires a reviewed migration or code correction; operators must not edit payload
JSON ad hoc.

## Failure behavior

| Failure window | Required outcome |
| --- | --- |
| Object verified, PostgreSQL transaction rolls back | No job/outbox exists; object is an orphan eligible for controlled cleanup |
| Job/outbox commit, API crashes before response | Client replay returns the same job; dispatcher still publishes |
| Commit succeeds, dispatcher is down | Event remains due in PostgreSQL and publishes after recovery |
| Dispatcher crashes before broker call | Lease expires; another dispatcher republishes the same event |
| Broker accepts, dispatcher crashes before recording acknowledgement | Same event may publish again; worker claim remains duplicate-safe |
| Broker rejects or times out | Event backs off without consuming a job execution attempt |
| Worker receives duplicate messages | PostgreSQL permits at most one valid fenced running attempt |
| Worker receives a stale message after cancellation/terminal state | Durable state reload produces a no-op |
| Published-row cleanup fails | Processing is unaffected; retention retries later |

## Consequences

- A committed job cannot lose its dispatch intent.
- Broker outages no longer determine whether upload/job creation can commit.
- At-least-once delivery creates expected duplicates, handled by durable claims and idempotency.
- PostgreSQL gains an operational table, dispatcher leases, retention, lag metrics,
  alerts, and recovery procedures.
- Queue and worker choices can change without changing job truth or the API contract.
- Users may see a job remain `pending` while publication is delayed, which is more
  accurate than falsely reporting it queued.

## Accepted initial defaults

| Topic | Recommendation | Why |
| --- | --- | --- |
| Delivery guarantee | At least once | Achievable across the database/broker boundary; duplicates are already safe |
| Job state after broker acknowledgement | Move `pending` or due `retry_scheduled` to `queued`; never reverse `running`/terminal state | Preserves the accepted ADR 0007 meaning of `queued` |
| Publication retry budget | Retry indefinitely with capped backoff | A finite limit can permanently strand otherwise valid work |
| Backoff | About 1s, 5s, 30s, 2m, then cap at 5m, with jitter | Fast transient recovery without hammering an outage |
| Alert threshold | 10 failed publications or oldest due event over 15 minutes | Makes sustained dispatch loss visible before users wait indefinitely |
| Published/discarded retention | 30 days | Supports diagnosis and replay review without making outbox a permanent audit log |
| Message contents | Event ID, type/version, job ID, server timestamp only | Minimizes disclosure and forces trusted PostgreSQL reload |
| Ordering | Per-job sequence only | Global ordering adds cost without a product requirement |
| User-facing replay | None; use successor-job retry | Keeps infrastructure recovery separate from authorized product actions |

## Deferred tuning

Exact dispatcher lease duration, claim batch size, polling cadence, and concurrency
remain deferred to ADR 0012 after the worker operating model is selected. Those
values may be tuned without weakening the accepted atomicity, retry, retention,
ordering, payload, authorization, or acknowledgement contracts.

## Acceptance evidence required

- Transaction rollback tests prove a job and its dispatch event are all-or-nothing.
- Concurrent same-key requests create one job and one initial dispatch event.
- Retry scheduling atomically creates exactly one due event per dispatch sequence.
- Two dispatchers cannot hold a valid lease on the same event simultaneously.
- Crash tests before publish and after broker acceptance eventually redeliver the
  same event without overlapping worker attempts.
- Broker failure and recovery do not consume job execution attempts or lose events.
- Cancellation and terminal-state races make stale delivery a safe no-op.
- Queue payload fixtures contain no tenant claims, object keys, filenames, content,
  credentials, raw provider errors, or secret-bearing configuration.
- Published/discarded retention cannot remove pending events or authoritative job history.
- Alembic upgrade/downgrade, model-drift, deterministic, and live-service gates pass.

## Implementation evidence on 2026-08-30

- Alembic revision `20260830_0007` adds tenant-constrained outbox events with stable
  event and job identity, unique per-job dispatch sequence, minimal versioned JSON,
  due time, recorded publication attempts, expiring leases, acknowledgement,
  discard, safe failure, and operational timestamps.
- A new job and dispatch sequence `1` are inserted in one caller-owned transaction.
  Retryable attempt failure and expired-lease recovery insert the next sequence in
  the same transaction as `retry_scheduled` and use `next_attempt_at` as availability.
- Repository claims use bounded `FOR UPDATE SKIP LOCKED`, reject overlapping active
  leases, and block a later event while an earlier sequence for that job remains
  unpublished and undiscarded.
- Publication start is recorded explicitly under the active lease immediately before
  the future broker call. A positive acknowledgement marks the event published and
  conditionally moves the matching `pending` or due `retry_scheduled` job to `queued`.
  Safe failure recording applies a future retry time without consuming a job attempt.
- Cancellation and terminal job transitions discard only unpublished events and
  clear their leases. Published evidence remains immutable, and stale in-flight
  delivery remains safe through PostgreSQL job reload and fencing.
- Payload fixtures contain only event ID, event type, schema version, job ID, and
  server timestamp. Workspace claims, filenames, object keys, document content,
  credentials, and raw dependency errors are absent.
- Deterministic tests prove transaction rollback, idempotent replay, ordered retry
  events, lease fencing, backoff, acknowledgement, and discard behavior. A live
  PostgreSQL test proves concurrent same-key requests create one job and one event
  and concurrent dispatchers cannot lease the same event.
- The migration upgrade, empty-table downgrade/upgrade cycle, model-drift check,
  100-test deterministic gate, and 103-test live gate pass. RabbitMQ publication,
  a long-running dispatcher, and workers remain outside this milestone.

## Runtime evidence on 2026-08-30

- The separate dispatcher now leases bounded batches, validates the strict ADR 0009
  payload, publishes the stable event identity through RabbitMQ confirms, and marks
  the job queued only after confirmation.
- Unconfirmed publication releases the event with capped safe backoff and does not
  consume a worker attempt. Aggregate operations alert at 10 attempts or 15 minutes.
- Preview-first retention deletes only published/discarded rows older than 30 days
  whose jobs are terminal. Tests prove pending events and job history remain intact.
