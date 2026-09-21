# Phase 11 pilot operations

Status: **Foundation implemented; live rollout disabled**

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
```

The contract gate enumerates login/logout, personal-workspace defaulting, upload/progress/cancel/retry,
library readiness, grounded chat/citations, structured feedback, access revocation,
support/pause handling, and backup/rollback readiness. Evidence contains no identities,
content, provider identifiers, or secrets.

## Deliberately unresolved live-pilot values

Before a two-user canary, separately approve the stage duration/minimum active-user
counts, support response target, feedback/evidence retention duration, exact consent
copy, named access approver, and the live acceptance rubric. A live-stage policy change
must be reviewed together with an invitation plan; changing the JSON alone grants no
authority to invite users or make external changes.
