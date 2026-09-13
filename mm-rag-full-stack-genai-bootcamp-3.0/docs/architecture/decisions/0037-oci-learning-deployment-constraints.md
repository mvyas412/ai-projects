# ADR 0037: OCI learning deployment constraints

- Status: Accepted
- Date: 2026-09-13
- Milestone: 8.0

## Context

Phase 8 needs a cloud-shaped deployment without turning a two-to-three-user learning
project into a paid production estate. The user prefers free resources, a US region,
no purchased domain, and pragmatic recovery rather than enterprise availability.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| AWS, Azure, or Google Cloud trial | Broad managed-service learning | Credits expire and the full persistent stack is unlikely to remain free |
| Federated free-tier services | More managed components | Vendor sprawl, public-network dependencies, and incompatible sleep/usage limits |
| OCI Always Free learning environment | Persistent compute and object-storage allowance; existing containers remain portable | Capacity is not guaranteed; idle resources may be reclaimed; no production SLA |

## Proposed decision

Use Oracle Cloud Infrastructure as the Phase 8 learning provider, targeting an
Always Free-eligible US home region with ARM capacity. The cost target is USD 0 per
month. No paid shape, automatic paid upgrade, or resource above the free allowance may
be enabled without explicit approval. Configure cost visibility and the lowest useful
budget alerts even when the planned spend is zero.

The pilot supports two to three authorized users and synthetic or non-sensitive
learning documents only. A provider hostname or free stable DNS name is acceptable;
buying a domain is not required. Use an initial recovery point objective of 24 hours
and recovery time objective of 8 hours, backed by nightly encrypted backups and a
monthly restore exercise.

## Recommendation

Approve OCI for the learning deployment and treat it as production-shaped evidence,
not a production availability claim. Choose the exact US home region only after the
account shows Always Free ARM capacity because the home-region choice is consequential.

## Approval questions

1. Approve OCI, a USD 0 target, and explicit approval before any paid resource?
2. Approve a two-to-three-user pilot using non-sensitive learning data?
3. Approve US placement, RPO 24 hours, and RTO 8 hours?

## Consequences

- The deployment must fit the free ARM, storage, and network allowances.
- Capacity or reclamation can interrupt the lab and is handled through reproducible
  provisioning and restore, not an availability claim.
- A future real production environment requires a new cost, availability, and data-
  residency decision.

## Decision record

Accepted by the user on 2026-09-13. OCI, the zero-cost guardrail, US placement,
two-to-three-user learning scope, no purchased domain, RPO 24 hours, and RTO 8 hours
are approved. No cloud resource or paid service was authorized by this decision.

## Capacity amendment — 2026-09-13

The user subsequently approved a free-first ten-user objective. The effective pilot
contract now supports at least ten registered authorized users, normal concurrency of
three to five active users, and an acceptance burst of ten simultaneous users. The
original two-to-three-user decision above remains the historical starting point.

The USD 0 target is unchanged. The single Always Free-eligible host must first be tested
against this workload; this amendment does not claim that unmeasured free capacity is
sufficient and does not authorize paid resources. If the free host misses the approved
SLOs, optimize within the free envelope first and present any paid or multi-node option
for separate approval.
