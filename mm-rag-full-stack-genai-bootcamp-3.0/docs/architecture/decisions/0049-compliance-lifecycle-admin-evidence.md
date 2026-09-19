# ADR 0049: Compliance lifecycle and administrative evidence

- Status: Proposed
- Date: 2026-09-19
- Milestone: 9.6

## Context

Phase 4 established governed retention and deletion. Enterprise administration must add
policy assignment, legal hold, subject/tenant export and deletion workflows, and
reviewable evidence across relational, vector, object, connector, and commercial state.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Manual runbooks only | Low implementation cost | Inconsistent scope and weak evidence |
| Vendor governance suite | Broad features | Cost, lock-in, and data replication |
| Product-owned lifecycle orchestration | Reuses existing controls | Requires careful cross-store checkpoints |

## Proposed decision

Extend the accepted tombstone/hold/purge model with versioned tenant policies and
authorized administrative workflows. Every preview has a stable scope fingerprint;
apply requires reauthorization and fails if scope changed. Legal hold blocks destructive
steps but not access revocation. Export and deletion run as durable checkpointed jobs,
cover connector mappings, identity links, usage/commercial records where legally
deletable, SQL, Qdrant, and object storage, and produce content-free checksummed evidence.
Separation of duties, purpose/reason codes, and append-only audit apply to privileged
actions. Automatic retention remains disabled until a reviewed schedule is approved.

## Recommendation

Approve product-owned orchestration first and defer an external compliance vendor.

## Approval questions

1. Approve preview/reauthorize/apply for destructive lifecycle actions?
2. Approve hold precedence and content-free evidence manifests?
3. Keep automatic retention disabled pending a separate schedule decision?

## Consequences

- Enterprise lifecycle evidence builds on existing tested controls.
- Jurisdiction-specific policy is not implied and needs legal review for real use.
- Provider integrations must expose deletion/export capabilities through adapters.
