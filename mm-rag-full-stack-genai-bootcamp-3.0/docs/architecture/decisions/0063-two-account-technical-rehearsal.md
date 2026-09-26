# ADR 0063: Two-account technical rehearsal boundary

- Status: Accepted
- Date: 2026-09-26
- Milestone: 11.5

## Context

The two approved Auth0 accounts are verified, activated, and controlled by one human
who accepted the pilot notice for both accounts. They can exercise account separation
and product workflows, but they cannot provide independent two-user product evidence.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Count both accounts as two users | Starts the formal clock immediately | Misrepresents one person as two independent participants |
| Wait for a second human | Preserves the formal Phase 11 evidence contract | Delays technical learning |
| Run a separately labeled two-account rehearsal | Exercises the system now without overstating evidence | Cannot satisfy the formal canary or expansion gates |

## Accepted decision

Run one bounded two-account technical rehearsal. Keep its evidence aggregate,
content-free, identity-free, and explicitly marked as non-product-validation. It may
exercise authentication, workspace isolation, core journeys, feedback, and operational
safeguards, but it does not start ADR 0062's three-day two-user clock, satisfy Phase 11
product acceptance, or authorize the five- or ten-user stages.

Paid model calls, access revocation, external communication, cloud changes, and other
separately gated actions still require their existing explicit approvals. Formal pilot
acceptance remains blocked until a second independent human participates or a later ADR
changes the product-validation objective.
