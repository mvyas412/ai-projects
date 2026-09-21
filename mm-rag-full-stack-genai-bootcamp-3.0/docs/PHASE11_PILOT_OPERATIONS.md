# Phase 11 pilot operations

Status: **Canary authorized; awaiting two private participant identities**

## Purpose

The Phase 11 controls provide a deterministic, content-free rehearsal of the pilot
control contract before any real participant is invited. This verifies policy and
evidence completeness; it is not evidence that a person completed the product UI. The
commands do not enroll users, call providers, spend money, change cloud resources,
promote Next.js, or enable automatic retention.

## Current commands

Validate the accepted policy:

```bash
make phase11-policy-check
```

Generate ignored synthetic evidence and validate it:

```bash
make phase11-rehearsal
make phase11-evidence-gate
make phase11-canary-readiness
```

The contract gate enumerates login/logout, personal-workspace defaulting, upload/progress/cancel/retry,
library readiness, grounded chat/citations, structured feedback, access revocation,
support/pause handling, and backup/rollback readiness. Evidence contains no identities,
content, provider identifiers, or secrets.

## Approved live-pilot defaults

- The workspace Owner approves and revokes access.
- Support is best effort within one business day.
- Aggregate evidence is retained for 30 days after closure and removed manually after
  review; automatic deletion remains disabled.
- Stage gates are 2 users/3 days/2 active, 5 users/7 days/3 active, and
  10 users/14 days/5 active.
- At least 90% of attempted core journeys must complete, while all safeguard gates must
  pass without exception.

The participant notice and bounded live execution are approved. The readiness command
remains blocked until exactly two participant identities are supplied through a private
operator workflow. Identities must never be placed in Git, aggregate evidence, logs, or
command output.

The accepted participant wording is maintained in
[the Phase 11 pilot notice and consent](PHASE11_PILOT_CONSENT.md).
