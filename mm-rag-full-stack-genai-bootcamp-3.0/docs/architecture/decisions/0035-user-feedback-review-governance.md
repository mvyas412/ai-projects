# ADR 0035: User feedback and review governance

- Status: Proposed
- Date: 2026-09-07
- Milestone: 7.3

## Context

Production feedback can identify regressions that synthetic fixtures miss, but a
thumb, comment, prompt, answer, or cited source can contain tenant-sensitive data.
Feedback must not become training/evaluation material automatically or create a new
cross-tenant review channel.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Store thumbs only | Minimal privacy risk | Little diagnostic value |
| Store every prompt/answer/source automatically | Rich examples | Excessive collection, unclear consent, and broad reviewer access |
| Explicit feedback with controlled snapshot and review promotion | Useful and governed | More UI, authorization, retention, and adjudication work |

## Proposed decision

Capture a rating and bounded reason category by default. Free-text explanation and a
diagnostic snapshot are separate explicit user actions with clear disclosure. The
snapshot references immutable authorized identities; it does not copy raw document
content into telemetry. PostgreSQL stores tenant-scoped feedback under RLS with
submitter, policy version, consent scope, status, reviewer, and retention metadata.

Only authorized workspace owners/admins may review workspace feedback. Promotion to
an evaluation regression case requires human redaction, license/provenance review,
stable expected evidence, a new synthetic/public-safe case where possible, and an
immutable approval record. Feedback never triggers automatic training, prompt
changes, or candidate promotion.

## Recommendation

Approve minimal structured feedback first, with optional explicitly consented detail.
Keep cross-tenant platform review and model-training use out of scope until a later
privacy/legal decision.

## Approval questions

1. Approve rating plus bounded reason categories as the default capture?
2. Require explicit consent for comments or diagnostic snapshots?
3. Limit review to authorized workspace owners/admins and prohibit automatic tuning?

## Consequences

- Feedback can improve regression coverage without becoming uncontrolled telemetry.
- Deletion, hold, export, and audit behavior must extend to feedback records.
- Platform-wide quality review remains unavailable until separately governed.

