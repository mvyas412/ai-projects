# ADR 0047: Immutable usage ledger, quotas, and entitlements

- Status: Accepted
- Date: 2026-09-19
- Milestone: 9.4

## Context

Commercial controls need explainable usage totals and race-safe enforcement. Telemetry is
not a billing ledger, and mutable counters alone cannot support correction or audit.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Count telemetry | Already emitted | Sampling, loss, and privacy mismatch |
| Mutable counters only | Fast reads | Weak audit and difficult reconciliation |
| Append-only ledger plus materialized balances | Auditable and correctable | More schema and concurrency work |

## Proposed decision

Record immutable tenant-scoped usage entries at authoritative product boundaries with a
stable idempotency key, meter/version, quantity, unit, resource reference, event time,
and correction linkage. Never store prompts, document text, or provider credentials.
Derive balances from the ledger and enforce quotas through transactional reservations
and settlement so concurrent requests cannot overspend. Entitlements are versioned,
time-bounded policy inputs; rate limits protect runtime independently from commercial
quota. Failed or cancelled work settles according to an explicit meter rule.

## Recommendation

Approve PostgreSQL as the initial immutable ledger and balance authority; defer external
metering vendors until evidence shows a need.

## Approval questions

1. Approve append-only usage entries plus reversible correction entries?
2. Approve transactional reserve/settle enforcement?
3. Which initial meters and free learning quotas should be exposed to users?

## Consequences

- Usage can be audited and replayed without treating telemetry as money.
- Meter definitions become versioned product contracts.
- Billing remains downstream and cannot mutate usage truth.

## Decision record

Accepted by the user on 2026-09-19. PostgreSQL is the initial append-only usage and
balance authority, corrections remain additive, and quota enforcement uses transactional
reserve/settle semantics. Initial meters and quota values remain TBD.
