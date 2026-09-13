# ADR 0039: OCI learning data plane and backups

- Status: Accepted
- Date: 2026-09-13
- Milestone: 8.0 and 8.4

## Context

Managed PostgreSQL, vector, and RabbitMQ services would simplify operations but are
unlikely to fit a durable zero-cost environment. The existing PostgreSQL, Qdrant,
RabbitMQ, and S3-compatible contracts already support portable containers and backups.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Fully managed services | Backups, patching, and scaling are easier | Ongoing cost and several additional provider decisions |
| Separate free-tier SaaS providers | Can reduce VM resource use | Vendor sprawl, free-tier suspension, public egress, and fragmented recovery |
| Self-host state on encrypted OCI block storage with off-host backups | Lowest cost and closest to the tested stack | Operator owns upgrades, capacity, backup, and restore |

## Proposed decision

For the learning pilot, run PostgreSQL, Qdrant, and RabbitMQ as private containers on
encrypted OCI block storage. Continue using the provider-neutral S3 adapter; validate
OCI Object Storage compatibility before selecting it for immutable application objects.
Use OCI Object Storage as the off-host destination for encrypted PostgreSQL backups,
Qdrant snapshots, configuration manifests, and checksums within the free allowance.

Do not claim high availability. Pin versions, apply least-privilege credentials,
enforce storage quotas, and test a clean-host restore. SeaweedFS remains the local/CI
implementation and rollback until the OCI object contract passes.

## Recommendation

Approve the self-hosted learning data plane plus off-host OCI backups. Revisit managed
services only if the free resource envelope or recovery evidence is inadequate.

## Approval questions

1. Approve self-hosted PostgreSQL, Qdrant, and RabbitMQ for the free pilot?
2. Approve OCI Object Storage only after the existing S3 contract passes against it?
3. Approve nightly backups, bounded retention, and monthly clean restore drills?

## Consequences

- The pilot remains inexpensive but carries a single-host failure domain.
- Backup and restore evidence becomes mandatory, not optional documentation.
- Production managed-service choices remain open for a future funded environment.

## Decision record

Accepted by the user on 2026-09-13. PostgreSQL, Qdrant, and RabbitMQ remain
self-hosted for the free pilot; OCI Object Storage must pass the existing S3 contract
before storing application objects and serves as the approved off-host backup target.
