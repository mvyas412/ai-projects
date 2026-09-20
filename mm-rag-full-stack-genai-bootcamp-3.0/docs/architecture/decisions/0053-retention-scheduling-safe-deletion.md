# ADR 0053: Governed retention scheduling and safe deletion execution

- Status: Proposed
- Date: 2026-09-19
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

## Proposed decision

Never schedule direct deletion. A scheduler may create an immutable preview only. A
workspace owner/admin must review and reauthorize the unchanged scope before execution;
holds always win, failures checkpoint safely, and a recovery window precedes physical
purge. Automatic execution remains disabled until schedule, review window, recovery
window, exemptions, and notification policy are explicitly accepted.

## Recommendation

Begin with preview-only monthly reports and no automatic apply. Consider execution only
after synthetic held/unheld data, stale-preview rejection, restore, and cross-store
reconciliation all pass.

## Approval questions

1. Approve preview-only scheduling as the first implementation boundary?
2. What retention and recovery windows should eventually apply?
3. Who may reauthorize execution, and what notification channel should be used?

## Consequences

- Phase 10 can improve lifecycle visibility without silently deleting data.
- Destructive scheduling remains blocked pending separate explicit approval.
