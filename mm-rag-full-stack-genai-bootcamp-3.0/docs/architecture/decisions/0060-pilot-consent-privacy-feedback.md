# ADR 0060: Pilot consent, privacy, and feedback

- Status: Accepted
- Date: 2026-09-20
- Milestone: 11.3

## Context

Real-user learning can create personal data and sensitive document content. Existing
telemetry is content-free and feedback is tenant-scoped, but pilot consent, allowed
feedback, retention, and evidence use need an explicit contract.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Collect raw sessions and prompts | Rich diagnostics | Excessive privacy and security risk |
| Collect no user feedback | Minimal data | Weak product-learning evidence |
| Voluntary structured feedback plus aggregate telemetry | Useful and bounded | Less diagnostic detail |

## Recommendation

Use plain-language pilot consent, voluntary structured feedback, and existing
content-free aggregate telemetry. Do not retain raw prompts, answers, documents,
identities, or provider identifiers in pilot evidence. Keep automatic retention apply
disabled until a separate policy decision.

## Accepted decision

Allow voluntary ratings in usability, answer relevance, evidence clarity, performance,
and accessibility categories. Pilot evidence remains aggregate and content-free.
Aggregate pilot evidence is retained for 30 days after closure and then removed through
a reviewed manual operation; automatic deletion and automatic retention apply remain
disabled. The participant-facing copy in `docs/PHASE11_PILOT_CONSENT.md` is accepted.
The Owner handles manual access-removal and deletion requests.
