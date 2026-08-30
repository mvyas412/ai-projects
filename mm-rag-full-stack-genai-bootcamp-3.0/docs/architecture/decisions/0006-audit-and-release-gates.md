# ADR 0006: Immutable workspace activity and automated release gates

- Status: Accepted
- Date: 2026-08-30
- Milestone: 2.5

## Context

Phase 2 must be demonstrable and reviewable, not merely runnable on one laptop.
Security-relevant product actions need attribution, and every change needs a
repeatable quality gate using production-shaped PostgreSQL and Qdrant services.

## Decision

1. PostgreSQL stores append-only audit events with workspace, actor, action,
   resource identity, safe structured details, and server-generated timestamp.
2. Events are written in the same transaction as the product mutation whenever
   possible. Index-completion events commit with the READY status.
3. Activity reads require workspace membership, return non-enumerating 404 for
   outsiders, are newest-first, and enforce a maximum result count.
4. Audit details contain identifiers and operational metadata—not tokens, secrets,
   raw credentials, connection strings, or full user/model message content.
5. CI runs locked dependency verification, Ruff, Mypy, Alembic upgrade/head check,
   live PostgreSQL/Qdrant readiness, the complete test suite, coverage, and diff hygiene.
6. Stable Makefile and shell entry points keep local and CI verification aligned.

## Consequences

- Users can inspect who performed major workspace actions without exposing secrets.
- Mutation/audit consistency is strong within the modular monolith transaction boundary.
- The activity stream is not yet a tamper-evident external compliance ledger; that
  enterprise capability remains a later governance phase.
- Release regressions are visible on the pull request before merge.
