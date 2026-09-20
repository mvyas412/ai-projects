# ADR 0056: Upgrade, rollback, and disaster-recovery automation

- Status: Proposed
- Date: 2026-09-19
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

## Proposed decision

Implement plan-first operator commands that validate revision, manifest, migration
compatibility, backup freshness, active jobs, disk headroom, and service health before
changing state. Use immutable digests, bounded quiescence, forward-only migrations,
post-change verification, and explicit rollback/restore branches. Clean-host recovery
must recreate infrastructure from reviewed IaC, then restore encrypted data without
placing secrets in Terraform, cloud-init, logs, or evidence.

## Recommendation

Automate preflight and verification first, then exercise in-place upgrade/rollback and
clean-host recovery separately. Keep final execution operator-authorized.

## Approval questions

1. Approve plan-first, operator-authorized execution rather than autonomous changes?
2. Must every release include both rollback compatibility and restore fallback evidence?
3. May a clean-host drill create temporary free-tier resources when separately approved?

## Consequences

- Routine changes and disaster recovery become reproducible.
- Host replacement, destructive cleanup, and temporary cloud resources remain explicit
  approval boundaries.
