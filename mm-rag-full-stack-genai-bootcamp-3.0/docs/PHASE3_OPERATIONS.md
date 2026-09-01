# Phase 3 ingestion operations

This runbook covers the free local/CI asynchronous-ingestion runtime. PostgreSQL is
authoritative for jobs, attempts, active generations, and outbox state. RabbitMQ is
only a wake-up channel; Qdrant vectors and object artifacts are generation-scoped.

## Start, stop, and inspect

1. Run `make services` to start PostgreSQL, Qdrant, SeaweedFS, and RabbitMQ.
2. Run `make migrate` and confirm the current Alembic head. On the completed
   Phase 4 branch this is `20260831_0013`.
3. Run `make runtime` to start the dispatcher and one worker independently.
4. Run `make operations-status` for aggregate, non-disclosing backlog health.
5. Run `make runtime-stop` to drain and stop only the execution processes.

The runtime profile is deliberate: dependency startup alone cannot consume queued
work or invoke a model. Dispatcher and worker health files contain only process
state, counters, and timestamps. They never contain credentials, object keys,
filenames, document content, or raw provider errors.

The worker refreshes readiness on every lease-recovery cycle, including while idle.
An aging worker heartbeat therefore indicates a stalled process rather than an empty
queue.

## Alerts and first response

Treat the operations report as unhealthy when any of these are true:

- a due unpublished outbox event is at least 15 minutes old;
- an unpublished event has at least 10 publication attempts;
- a running attempt has an expired lease; or
- a runtime process is not healthy.

Check service health, then broker health, then `make operations-status`. Restarting
the dispatcher is safe because unpublished events retain stable IDs. The worker
automatically fences and recovers expired attempts. Do not edit outbox payloads,
reopen terminal jobs, purge the main queue, or treat the dead-letter queue as job truth.

For a member-requested retry, use the public successor-job action. A terminal job
remains immutable. A malformed dead-letter message is operational evidence and can
be removed only after its PostgreSQL job/outbox state is understood.

## Retention

`make operations-retention-preview` reports candidates without deleting anything.
The explicit command `python -m backend.app.workers.operations retention-apply`
deletes only published or discarded outbox rows older than 30 days whose jobs are
already terminal. It cannot delete pending events or job/attempt/audit history.

Phase 4 ADR 0017 now governs inactive-generation, orphan-object, terminal-job,
audit, document, and conversation lifecycle. Use the owner-reviewed preview/apply
flow in [the Phase 4 governance runbook](PHASE4_GOVERNANCE_OPERATIONS.md). No
destructive lifecycle batch runs automatically.

## PostgreSQL backup and restore exercise

Create a private, ignored logical backup:

```bash
./scripts/backup_phase3_postgres.sh
```

The command writes a mode-`0600` custom-format dump and SHA-256 sidecar below
`data/runtime/backups/` by default. Never commit, share, or screen-share backups.

Exercise restore safety against a newly created temporary database:

```bash
./scripts/verify_phase3_postgres_restore.sh data/runtime/backups/phase3-postgres-TIMESTAMP.dump
```

The verifier checks the digest, restores without changing the live database,
verifies migration head plus durable ingestion and Phase 4 lifecycle tables, then
drops only its generated temporary restore database.

SeaweedFS data must be protected with a consistent provider/volume snapshot in the
same recovery set as PostgreSQL. Qdrant generations are derived from immutable
originals and manifests, but a deployment recovery plan should snapshot Qdrant as
well to shorten recovery time. Production backup provider, encryption, retention,
PITR, and disaster-recovery targets remain Phase 8 infrastructure decisions.

## Release checks

Run `make check`, then `make check-live`. The live gate includes PostgreSQL/Qdrant,
SeaweedFS, RabbitMQ topology/confirm/manual-ack behavior, FastAPI, and Streamlit.
It does not run the paid OpenAI acceptance suite. Run `make check-acceptance` only
with explicit authorization for paid model requests.
