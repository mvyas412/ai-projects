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
Exact retention duration, consent text, and the manual access/removal request procedure
must be approved before live collection; automatic retention apply remains disabled.
