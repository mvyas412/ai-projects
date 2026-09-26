# Phase 11 pilot operations

Status: **Two-account technical rehearsal authorized; formal two-user canary blocked**

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
make phase11-technical-template
make phase11-technical-gate
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

Exactly two approved account identities were supplied through the private operator
workflow and are not present in Git or aggregate evidence. Both are verified, have
participant-controlled credentials, and completed authenticated Personal-workspace
login. Auth0 public database signup and MM-RAG Google social login remain disabled.

One human accepted the participant notice for both accounts. ADR 0063 therefore permits
a clearly labeled two-account technical rehearsal while preserving ADR 0062's formal
two-user gate. The rehearsal does not start the three-day clock, satisfy product-user
validation, or authorize expansion. `make phase11-canary-readiness` reports the
technical rehearsal ready and the formal canary blocked on a second independent human.
The technical-template command creates ignored, identity-free evidence with every live
scenario pending. Operators update only aggregate statuses and provider-call/cost totals;
the technical gate cannot convert that evidence into formal product validation.

The accepted participant wording is maintained in
[the Phase 11 pilot notice and consent](PHASE11_PILOT_CONSENT.md).
