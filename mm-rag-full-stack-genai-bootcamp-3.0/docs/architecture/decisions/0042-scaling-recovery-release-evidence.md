# ADR 0042: Scaling, recovery, and release evidence

- Status: Accepted
- Date: 2026-09-13
- Milestone: 8.0 and 8.3–8.5

## Context

A free single-host pilot cannot prove high availability, but it can prove bounded load,
backpressure, graceful restart, repeatable rebuild, and restore. Those are useful
prerequisites before spending money on horizontal infrastructure.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Claim production readiness from functional tests | Fast | No load, failure, or recovery evidence |
| Build multi-region/high availability immediately | Strong architecture exercise | Cost and complexity exceed the learning objective |
| Bounded single-host load and recovery exercises | Honest, affordable evidence | Does not provide an uptime SLA |

## Proposed decision

Define a two-to-three-user representative load profile after Phase 7 freezes its pilot
SLOs. Exercise API concurrency, ingestion backpressure, worker restart, broker delay,
database/vector/object unavailability, telemetry loss, disk pressure, graceful deploy,
rollback, and full clean-host restore. Preserve authorization, citation, calculation,
and durable-job invariants under every fault.

Acceptance requires meeting the approved Phase 7 latency/error targets within the
free resource envelope, RPO 24 hours, RTO 8 hours, zero security/integrity escapes,
documented capacity limits, and a cost report showing no unapproved paid resource.

## Recommendation

Approve evidence-first scaling. Treat measured saturation as the trigger for a later
paid or multi-node decision rather than pre-provisioning complexity.

## Approval questions

1. Approve the two-to-three-user load profile after Phase 7 target approval?
2. Approve the fault and clean-restore exercises as Phase 8 release gates?
3. Keep high availability, Kubernetes, and multi-region deployment out of this pilot?

## Consequences

- Phase 8 can close with honest recovery and capacity evidence without an uptime SLA.
- The single-host ceiling is documented rather than hidden.
- Any scale-out decision will be based on measured demand and an explicit budget.

## Decision record

Accepted by the user on 2026-09-13. Phase 8 must prove bounded load, safe failure,
rollback, cost, and clean restore without claiming high availability for the free pilot.
