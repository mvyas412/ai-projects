# ADR 0058: Pilot onboarding, account lifecycle, and support

- Status: Accepted
- Date: 2026-09-20
- Milestone: 11.1

## Context

A bounded pilot needs controlled admission, clear user expectations, reversible access,
and a support route without introducing public signup or a new identity provider.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Public self-service signup | Low operator effort | Abuse, support, and privacy exposure |
| Manual invitation using existing Auth0 | Simple and bounded | Operator effort for each participant |
| Add invitation/support providers | Better automation | New credentials, cost, and data processors |

## Recommendation

Use manually approved invitations with existing Auth0 and current workspace roles.
Keep support and notices in the application plus a documented manual operator path; do
not add an email, ticketing, or notification provider for the initial pilot.

## Accepted decision

Use manually approved and revocable access through existing Auth0. Participants begin
in a personal workspace. Support remains an in-application/manual operator path with no
new provider. The workspace Owner approves and revokes access. The learning-pilot
support target is best effort within one business day, with no emergency guarantee.
