# ADR 0055: OCI capacity, monitoring, and cost guardrails

- Status: Proposed
- Date: 2026-09-19
- Milestone: 10.4

## Context

The accepted Phoenix deployment supports the ten-user learning target on a free-first
single host. That host is also a correlated failure domain for CPU, memory, disk,
certificates, containers, queues, and backups. Silent saturation or an accidental paid
resource would undermine the learning objective.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Observe manually | No new components | Failures and cost drift can remain unnoticed |
| Add paid managed monitoring/autoscaling | Stronger operations | Violates the current budget goal |
| Free-first host/provider guardrails and safe degradation | Low cost and sufficient for learning | No high-availability claim |

## Proposed decision

Use existing telemetry plus bounded host/provider inventory checks for CPU, memory,
disk/inodes, queue age, service readiness, certificate expiry, backup age, and budget.
Define warning/critical thresholds and safe degradation/backpressure before considering
capacity changes. Keep the USD 1 budget alarm and an allowlist of expected free resources.
No auto-scaling or paid shape is authorized.

## Recommendation

Approve free-first monitoring for the ten-user target, with alerts recorded locally and
in existing provider budget channels before selecting external paging.

## Approval questions

1. Approve the ten-user learning target and no production-SLA claim?
2. Approve free/local alerting plus the existing OCI budget alarm?
3. What sustained threshold should trigger a reviewed capacity decision?

## Consequences

- Capacity and cost risk become measurable without creating paid infrastructure.
- High availability and automatic scaling remain explicitly out of scope.
