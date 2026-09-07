# ADR 0036: Dashboards, alerts, runbooks, and incident learning

- Status: Proposed
- Date: 2026-09-07
- Milestone: 7.4–7.5

## Context

Telemetry is useful only when operators can recognize user impact and take a safe,
documented action. Alerting every exception creates noise, while dashboards without
ownership or runbooks do not support recovery.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Dashboards only | Easy and quiet | Failures are noticed manually and late |
| Alert on every exception | Broad coverage | Severe alert fatigue and no user-impact prioritization |
| SLO burn-rate and invariant alerts with owned runbooks | Actionable and measurable | Requires ownership, testing, and maintenance |

## Proposed decision

Create versioned dashboards for product/API health, ingestion, retrieval/answer
quality, dependencies, security invariants, resource growth, and provider cost.
Every alert must name its owner, user impact, severity, evidence link, runbook,
silence window, and recovery condition. Use multi-window SLO burn-rate alerts for
service degradation and immediate alerts only for zero-tolerance security/integrity
invariants or durable data-loss risk.

Development uses dashboard-visible test alerts without paging. External notification
channels remain undecided until the user chooses a destination. Runbooks cover safe
diagnosis, rollback/degradation, queue drain, provider outage, object/vector/database
failure, telemetry loss, and evidence-preserving escalation. Incident reviews record
sanitized timelines, contributing controls, corrective actions, owners, and resulting
regression cases without private content.

## Recommendation

Approve dashboard-first operation and actionable burn-rate/invariant alerts. Do not
select Slack, email, PagerDuty, or another notification provider during kickoff.

## Approval questions

1. Approve the dashboard families and alert metadata contract?
2. Approve burn-rate alerts plus immediate zero-tolerance invariant alerts?
3. Keep external notification channels disabled until separately selected?

## Consequences

- Alert tests and runbook drills become release evidence.
- Development remains free and non-paging.
- A future production notification provider can be added without changing signal names.

