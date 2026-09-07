# ADR 0033: SLI, SLO, and error-budget contract

- Status: Proposed
- Date: 2026-09-07
- Milestone: 7.0 and 7.4–7.5

## Context

The project has release tests and readiness checks but no approved service-level
objectives. Arbitrary targets would create false confidence before representative
traffic exists, while waiting for production would leave Phase 8 without operating
requirements.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Copy generic 99.9% targets | Simple | Ignores pilot scale, model latency, and dependency behavior |
| Alert on every error or fixed threshold | Easy to configure | Noisy, unactionable, and encourages alert fatigue |
| Baseline first, then freeze pilot SLOs and burn-rate policy | Evidence-based and reviewable | Requires a measurement window before final targets |

## Proposed decision

Define versioned SLIs now and freeze numeric pilot SLOs after a seven-day local or
staging baseline plus representative fault exercises. Initial SLI families are:

- authenticated API availability and unexpected error ratio;
- query time-to-first-byte and completion latency by retrieval/model profile;
- ingestion queue delay, end-to-end completion latency, terminal success, retries,
  lease recovery, and dead-letter volume;
- retrieval/citation identity validity, safe abstention, and accepted quality gates;
- dependency readiness and telemetry delivery health; and
- model calls, tokens, object/vector growth, CPU/memory, and estimated cost per job
  and answer.

Authorization escapes, secret leakage, invalid citation identity, and unsafe exact
calculations remain zero-tolerance release failures rather than averaged SLOs.
Expected authorization denials, validation failures, and user cancellations do not
count as service errors. Use multi-window error-budget burn rates for actionable
alerts and suspend risky promotions when the approved budget is exhausted.

## Recommendation

Approve the SLI definitions and evidence-first target process. Do not invent 99.9%
claims before the baseline exists. Freeze concrete pilot targets in this ADR before
Milestone 7.4 dashboards and alerts are accepted.

## Approval questions

1. Approve the seven-day baseline before freezing numeric pilot SLOs?
2. Approve the proposed SLI families and zero-tolerance security/identity gates?
3. Approve error-budget burn rate, rather than raw error count, as the alert basis?

## Consequences

- Phase 7.1 instrumentation precedes final numeric target acceptance.
- Dashboards distinguish expected product outcomes from operational failures.
- Promotion policy can use both quality gates and remaining reliability budget.

