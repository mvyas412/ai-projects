# ADR 0062: Pilot rollout, acceptance, and rollback

- Status: Proposed
- Date: 2026-09-20
- Milestone: 11.5

## Context

A pilot needs staged exposure, explicit stop conditions, and a conclusion that does not
silently become an indefinite public service.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Invite all users at once | Fast | Poor fault isolation and harder support |
| Run indefinitely | More data | Unbounded obligation and stale consent |
| Stage 2 → 5 → 10 users with gates | Bounded learning and rollback | Slower expansion |

## Recommendation

Use internal rehearsal, two-user canary, five-user stage, then ten-user maximum. Require
authorization, task completion, reliability, cost, privacy, accessibility, backup, and
rollback gates at every stage. End with an explicit accept, remediate, or stop decision.

## Questions for approval

- What minimum duration and active-user count should each stage require?
- Which failures require immediate access freeze or rollback?
- What evidence is sufficient to accept Phase 11?
