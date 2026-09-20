# ADR 0055: OCI capacity, monitoring, and cost guardrails

- Status: Accepted
- Date: 2026-09-20
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

## Decision

Use existing telemetry plus bounded host/provider inventory checks for CPU, memory,
disk/inodes, queue age, service readiness, certificate expiry, backup age, and budget.
Define warning/critical thresholds and safe degradation/backpressure before considering
capacity changes. Keep the USD 1 budget alarm and an allowlist of expected free resources.
No auto-scaling or paid shape is authorized.

## Accepted defaults

- Keep the ten-user learning target and make no production-SLA claim.
- Use free/local alerting plus the existing OCI budget alarm; do not select external
  paging or paid monitoring.
- Trigger a reviewed capacity decision when CPU, memory, disk, or inode use remains at
  or above 80% for 15 minutes. Treat 90% resource use, excessive queue age, an overdue
  backup, or impending certificate expiry as critical; refine service-specific
  thresholds through controlled free tests.
- Keep auto-scaling and paid OCI shapes disabled.

## Consequences

- Capacity and cost risk become measurable without creating paid infrastructure.
- High availability and automatic scaling remain explicitly out of scope.
