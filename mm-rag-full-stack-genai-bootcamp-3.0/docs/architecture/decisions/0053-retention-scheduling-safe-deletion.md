# ADR 0053: Governed retention scheduling and safe deletion execution

- Status: Accepted
- Date: 2026-09-20
- Milestone: 10.2

## Context

The product already supports tombstones, holds, exact previews, reauthorization, and
checkpointed purge, but automatic retention is intentionally disabled. Scheduling it
turns a reviewed administrative tool into recurring destructive automation.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Keep automatic retention disabled | Lowest data-loss risk | Storage grows and lifecycle remains manual |
| Schedule direct deletion | Simple | Unacceptable stale-scope and hold-bypass risk |
| Schedule preview, notify, reauthorize, then execute | Governed and auditable | Requires policy, review window, and recovery decisions |

## Decision

Never schedule direct deletion. A scheduler may create an immutable preview only. A
workspace owner/admin must review and reauthorize the unchanged scope before execution;
holds always win, failures checkpoint safely, and a recovery window precedes physical
purge. Automatic execution remains disabled until schedule, review window, recovery
window, exemptions, and notification policy are explicitly accepted.

## Accepted defaults

- Generate one preview-only report monthly and keep automatic apply disabled.
- An owner or admin must review and reauthorize an unchanged preview through the
  existing administrative product boundary; holds always win.
- Use the application administrative view as the initial notification surface; do not
  select an external notification provider yet.
- Retention and recovery-window values remain undecided until measured storage growth
  supports a separate policy decision.

## Consequences

- Phase 10 can improve lifecycle visibility without silently deleting data.
- Destructive scheduling remains blocked pending separate explicit approval.
