# ADR 0048: Billing, subscription, and reconciliation boundary

- Status: Proposed
- Date: 2026-09-19
- Milestone: 9.5

## Context

The learning system needs a credible commercial architecture without collecting real
payments. Subscription state, product entitlements, and measured usage are related but
must not become one mutable provider-owned record.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Provider is product truth | Less local state | Outage and webhook errors directly corrupt access |
| Build payment processing | Maximum control | Security/compliance burden is out of scope |
| Provider adapter plus local commercial ledger | Portable and reconcilable | More explicit state transitions |

## Proposed decision

Keep the immutable usage ledger authoritative for measured usage and a versioned local
entitlement record authoritative for product access. A billing adapter maps plans,
subscriptions, invoices, and provider events to those records. Verify signed webhooks,
store minimal idempotent event envelopes, process them asynchronously, and reconcile on
a schedule. Outages retain the last valid entitlement for a bounded grace period; they
must not silently grant upgrades or erase debt/corrections.

Use sandbox or simulated billing only in Phase 9 learning work. Do not collect payment
card data. No billing provider is selected here.

## Recommendation

Approve the adapter/reconciliation boundary and evaluate Stripe test mode, Paddle
sandbox, and a fully simulated provider against free access and learning goals later.

## Approval questions

1. Approve separation of usage, entitlement, and provider subscription truth?
2. Approve signed idempotent webhooks plus scheduled reconciliation?
3. Keep Phase 9 payment activity sandbox/simulated only?

## Consequences

- Product access remains explainable during provider outages.
- Real-money launch requires a separate legal, tax, privacy, and operational review.
- Provider selection remains open.
