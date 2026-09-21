# ADR 0062: Pilot rollout, acceptance, and rollback

- Status: Accepted
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

## Accepted decision

Use the ordered internal, two-user, five-user, and ten-user stages. The two-user canary
runs at least three days with both users active; the five-user stage runs at least seven
days with three active users; the ten-user stage runs at least fourteen days with five
active users. Only internal synthetic rehearsal is enabled initially. Every stage must
preserve safety, authorization, privacy, integrity, free-first cost, backup, and rollback
gates; Phase 11 closes only through an explicit accept, remediate, or stop decision.
