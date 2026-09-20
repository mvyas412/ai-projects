# ADR 0056: Upgrade, rollback, and disaster-recovery automation

- Status: Accepted
- Date: 2026-09-20
- Milestone: 10.5–10.6

## Context

Phase 8 proved one immutable-digest rollback/roll-forward and one restore. Operators
still need a repeatable way to preflight upgrades, quiesce safely, apply migrations,
verify the data plane, roll back compatible changes, and rebuild a lost learning host.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Keep command-by-command runbooks | Flexible | Error-prone and dependent on one operator |
| Fully autonomous upgrades and recovery | Fast | Excessive authority and destructive risk |
| Reviewed plans with guarded automation | Repeatable and auditable | Requires explicit state and compatibility contracts |

## Decision

Implement plan-first operator commands that validate revision, manifest, migration
compatibility, backup freshness, active jobs, disk headroom, and service health before
changing state. Use immutable digests, bounded quiescence, forward-only migrations,
post-change verification, and explicit rollback/restore branches. Clean-host recovery
must recreate infrastructure from reviewed IaC, then restore encrypted data without
placing secrets in Terraform, cloud-init, logs, or evidence.

## Accepted defaults

- Use plan-first, operator-authorized execution rather than autonomous changes.
- Every application release provides rollback compatibility or, when rollback is unsafe,
  a tested restore fallback.
- Preflight revision, image digest, backup age, migration compatibility, disk headroom,
  active jobs, and service health before changing state.
- A clean-host drill may create temporary free-tier resources only after a separately
  reviewed zero-cost plan and explicit approval.
- Secrets never enter Terraform, cloud-init, logs, or evidence.

## Consequences

- Routine changes and disaster recovery become reproducible.
- Host replacement, destructive cleanup, and temporary cloud resources remain explicit
  approval boundaries.
