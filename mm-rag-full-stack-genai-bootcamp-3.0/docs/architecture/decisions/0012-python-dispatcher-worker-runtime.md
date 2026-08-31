# ADR 0012: Purpose-built Python dispatcher and ingestion worker runtime

- Status: Accepted
- Date: 2026-08-30
- Milestone: 3.0

## Context

ADRs 0007–0011 define durable jobs and attempts, immutable output promotion, the
transactional outbox, RabbitMQ delivery, and S3-compatible object storage. Phase 3
still needs an execution runtime that applies those contracts without introducing a
second retry scheduler, state machine, or source of truth.

The existing backend is Python/FastAPI and already owns parsing, enrichment,
embedding, PostgreSQL, and Qdrant integration. The runtime should reuse those domain
services while keeping API, dispatcher, and worker failure domains separate.

## Decision drivers

- Preserve PostgreSQL as the only authoritative job and attempt state machine.
- Keep RabbitMQ as a wake-up mechanism, not a workflow database.
- Reuse the tested Python ingestion domain without calling HTTP APIs internally.
- Support fenced leases, heartbeats, cancellation, bounded concurrency, and graceful shutdown.
- Make retries and output promotion follow ADRs 0007–0009 exactly.
- Run free and locally without a commercial workflow platform.
- Allow independent dispatcher and worker scaling.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Purpose-built Python dispatcher and worker | Exact fit for accepted contracts, direct domain reuse, minimal new framework semantics | We must implement supervision, metrics, leases, shutdown, and broker integration carefully |
| Celery | Mature task ecosystem, retries, scheduling, monitoring | Its task state/retry model can compete with PostgreSQL and obscure fencing/outbox boundaries |
| Dramatiq | Smaller Python worker framework with broker middleware | Still introduces framework retry/ack semantics that must be disabled or reconciled |
| Temporal | Powerful durable workflows and visibility | Adds a separate durable workflow authority, substantial infrastructure, and a different programming model |
| Run ingestion in FastAPI background tasks | Very simple deployment | Work is tied to API process lifetime, has weak recovery, and cannot scale or drain independently |
| One combined dispatcher/worker process | Fewer commands | Couples broker publication to expensive ingestion and complicates independent scaling and failure isolation |

## Decision

Build two small, purpose-built Python processes inside the Phase 3 backend package:

- an outbox dispatcher that leases PostgreSQL events and publishes confirmed messages
  to RabbitMQ; and
- an ingestion worker that consumes messages, reloads and claims jobs from PostgreSQL,
  executes the domain pipeline, heartbeats the fenced attempt, promotes verified
  outputs, commits the durable result, and then acknowledges the message.

They share application configuration, database models, repositories, typed domain
services, telemetry conventions, and safe error codes with FastAPI. They do not call
the public HTTP API and do not import Streamlit code.

This runtime is free local application code. It does not select managed orchestration,
commercial monitoring, or production hosting.

### Process boundaries

Provide explicit commands such as:

```text
python -m app.workers.outbox_dispatcher
python -m app.workers.ingestion_worker
```

Each process owns its event loop, database connections, RabbitMQ connection, health
state, and shutdown lifecycle. Docker Compose runs them as separate services. A
process crash must not crash FastAPI or corrupt a job.

### Dispatcher operating contract

The initial dispatcher defaults are:

| Setting | Initial value |
| --- | --- |
| Claim batch | Up to 50 due outbox events |
| Lease duration | 30 seconds |
| Idle poll cadence | About 1 second with bounded jitter |
| Publish mode | Sequential confirmed publish per leased event initially |
| Retry/backoff | ADR 0009 schedule and 5-minute cap |

The dispatcher renews or abandons safely before lease expiry, uses stable event IDs,
and records publication only after a positive RabbitMQ confirm. A lost or ambiguous
confirm leaves the event eligible for duplicate-safe redispatch.

### Worker operating contract

The initial worker defaults are:

| Setting | Initial value |
| --- | --- |
| In-flight jobs | 1 per worker process |
| RabbitMQ prefetch | 1 |
| Attempt lease | 60 seconds |
| Heartbeat cadence | 15 seconds |
| Execution attempts | Maximum 3 under ADR 0007 |
| Scale model | More independent worker processes |

Before reading a source object or invoking parsing/embedding, the worker reloads the
job by ID and atomically claims an eligible attempt with a fresh fencing token. It
must stop mutation if heartbeat renewal or fenced writes fail. Every SQL, object,
and vector operation remains scoped to the trusted job workspace and stable
document/version identity.

The first public progress contract remains stage plus completed/total units where a
total is meaningful. Progress is durable, monotonic within a stage, rate-limited,
and safe to expose. Logs may be richer but must not become the public contract.

### Cancellation

Cancellation is cooperative:

- a job cancelled before its first successful promotion performs no visible promotion;
- a queued or retry-scheduled job becomes terminal without starting a new attempt;
- a running worker checks cancellation between safe stages and before every promotion;
- blocking third-party work may finish before the next checkpoint, but its result is
  not promoted after cancellation wins the fenced transition; and
- temporary objects or vectors from a cancelled attempt remain invisible and are
  eligible for controlled cleanup.

“Before first promotion” means before any attempt output is atomically made the
current visible document version or generation. Uploading the immutable original is
not a promotion; it may remain as an orphan until cleanup if job creation rolls back.

### Graceful shutdown

On `SIGTERM` or `SIGINT`, each process stops accepting new work. The dispatcher stops
claiming new rows and finishes or releases its current bounded batch. The worker
stops consuming new messages and receives up to 120 seconds to reach a safe checkpoint.

If a worker cannot finish safely in that period, it closes without acknowledging the
message. Its attempt lease eventually expires and ADR 0007 recovery permits a new
fenced attempt. Shutdown must never mark success speculatively.

### Acknowledgement and failure rules

- Acknowledge only after the required PostgreSQL transition commits.
- A successful attempt acknowledges after verified immutable promotion, vector/SQL
  visibility commit, terminal job transition, and safe audit event.
- A retryable failure acknowledges only after `retry_scheduled` and the next outbox
  event commit atomically.
- A terminal failure acknowledges only after the terminal state and safe error code commit.
- A transient infrastructure failure before a durable transition leaves the broker
  message unacknowledged for redelivery.
- Duplicate, stale, cancelled, or terminal delivery becomes a PostgreSQL-validated no-op.

Provider exceptions are mapped to stable retryable or terminal codes. Raw exception
text, credentials, object keys, document content, and tenant-sensitive details stay
out of public status and routine logs.

### Health and observability

The dispatcher and worker expose process health suitable for Docker health checks
without opening a public administrative API. Required telemetry includes:

- running/ready state and dependency connectivity;
- outbox claim, confirmation, retry, lag, and lease-loss counts;
- worker claim, heartbeat, stage duration, attempt outcome, cancellation, and fence-loss counts;
- current in-flight count and controlled shutdown state; and
- stable correlation by job, attempt, outbox event, and trace IDs.

Metrics and logs must remain tenant-safe and non-disclosing. Queue depth, process
health, and PostgreSQL job state are reported separately.

## Consequences

- The implementation stays aligned with the accepted PostgreSQL state machine.
- API, dispatcher, and worker can scale and fail independently.
- Custom code must receive strong concurrency, crash-window, and shutdown testing.
- Framework-level convenience features are intentionally traded for explicit domain correctness.
- One-job-per-process is conservative initially but creates predictable memory and lease behavior.

## Accepted initial defaults

| Topic | Initial value |
| --- | --- |
| Runtime | Purpose-built async Python processes |
| Process separation | FastAPI, dispatcher, and worker run separately |
| Worker concurrency | 1 in-flight job per process |
| Dispatcher batch | 50 |
| Dispatcher lease | 30 seconds |
| Dispatcher idle poll | About 1 second with jitter |
| Attempt lease | 60 seconds |
| Attempt heartbeat | 15 seconds |
| Graceful shutdown | Up to 120 seconds at safe checkpoints |
| Cancellation | Cooperative; always checked before promotion |
| Job truth and retries | PostgreSQL under ADR 0007 |

## Acceptance evidence required

- API, dispatcher, and worker start and stop independently.
- Two dispatchers cannot publish one event as two different event identities.
- Two workers cannot hold valid fenced ownership of one attempt concurrently.
- Worker death before acknowledgement causes safe redelivery and eventual lease recovery.
- Heartbeat loss prevents stale SQL, vector, or object promotion.
- Cancellation before promotion leaves the prior visible version unchanged.
- Retryable failure atomically schedules the next dispatch without exceeding three attempts.
- Graceful shutdown drains or leaves unacknowledged work recoverable within the stated bound.
- Scale-out preserves tenant scope, bounded prefetch, and one in-flight job per process.
- Public status, logs, metrics, and broker messages contain no secrets or sensitive payloads.
