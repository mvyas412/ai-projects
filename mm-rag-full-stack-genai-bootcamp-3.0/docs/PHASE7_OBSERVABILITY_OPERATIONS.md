# Phase 7 evaluation and observability operations

This runbook covers the free local Phase 7 telemetry, evaluation, feedback, dashboard,
alert, and incident-learning controls. Telemetry is operational metadata only. Audit,
retrieval evidence, calculation traces, and durable job state remain authoritative.

## Start and validate

1. Run `make services`, `make observability`, and `make migrate`.
2. Start the API, dispatcher, worker, and UI normally. Their only telemetry export
   destination is the local OpenTelemetry Collector.
3. Run `make observability-status`; collector and Grafana must report ready.
4. Open Grafana at `http://localhost:3003` and use the provisioned MM-RAG dashboards.
5. Run `make phase7-evaluation`. Required evaluation remains deterministic and free.

Collector or backend loss must not fail a product request or job. Never troubleshoot by
adding prompts, answers, source text, credentials, object keys, SQL statements, or raw
exception stacks to telemetry.

## Seven-day SLO baseline

Run `make observability-baseline` once on each representative local/staging day. The
ignored baseline contains only aggregate numeric measurements and timestamps. Run
`make observability-baseline-status` to verify seven distinct days spanning at least six
elapsed days. Numeric pilot SLOs must then be reviewed and frozen in ADR 0033 before
the error-budget alerts become release authority.

## Error-budget burn

Confirm actual user impact in the overview, API, ingestion, and quality dashboards.
Pause risky promotion; do not disable authorization, citation validation, calculation
validation, or durable job fencing to recover budget. Check the affected dependency and
use the established rollback profile where appropriate. Recovery requires both alert
windows below threshold and a successful free release gate.

## Zero-tolerance invariant

Stop the candidate promotion immediately. Preserve the sanitized trace ID plus the
authoritative security audit, retrieval/evidence record, or calculation trace. Do not
copy private content into an incident record. Escalate to the workspace owner and record
the failed invariant, affected release, timeline, corrective owner, and regression test.

## Telemetry loss

Verify Collector health, bounded queue pressure, and the LGTM backend. Product traffic
continues while telemetry is degraded. Restart only the observability profile if needed;
do not restart healthy application services merely to reconstruct missing telemetry.
Recovery requires two successful export windows and a visible new metadata-only trace.

## Queue or worker degradation

Use `make operations-status`, then inspect correlated outbox/worker spans by job ID.
PostgreSQL remains job truth. Do not edit outbox payloads, reopen terminal jobs, or purge
RabbitMQ as a shortcut. Existing fenced recovery and successor-retry rules still apply.

## Incident learning

Copy `docs/incidents/INCIDENT_TEMPLATE.md` into the ignored incident workspace unless a
sanitized version is explicitly approved for Git. Record times, safe identifiers,
impact, controls, root causes, corrective owners, and regression-case IDs. Never include
customer text, prompts, answers, tokens, credentials, storage keys, or unrestricted logs.
