# ADR 0045: Incremental sync, source ACL, and deletion contract

- Status: Proposed
- Date: 2026-09-19
- Milestone: 9.2

## Context

Enterprise search becomes unsafe when content, permissions, or deletions lag behind the
source. Providers may deliver duplicates, reordered events, expiring cursors, partial
pages, and incomplete webhook hints.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Scheduled full crawl | Simple model | Slow, expensive, and stale between crawls |
| Webhooks only | Low latency | Loss, duplication, and provider-specific gaps |
| Durable delta sync plus reconciliation | Correct and recoverable | More state-machine and evidence work |

## Proposed decision

Use durable tenant/source sync runs with immutable attempts, fenced leases, opaque
provider cursors, and transactional checkpoint promotion. Webhooks are hints that enqueue
sync; periodic reconciliation remains authoritative. Canonical source object/version and
principal-set fingerprints make replay idempotent.

Permission contraction and source deletion must hide affected content from new retrieval
before asynchronous vector/object cleanup. Expansion becomes visible only after the new
permission snapshot and searchable generation are atomically promoted. Cursor expiry or
ambiguous provider state triggers a bounded rescan, not guessed continuation.

## Recommendation

Approve the durable delta-plus-reconciliation model with deny-first permission and
deletion propagation.

## Approval questions

1. Approve webhooks as hints and checkpoints/reconciliation as truth?
2. Approve immediate search denial before physical cleanup?
3. What permission/deletion propagation objective should the first connector prove?

## Consequences

- Stale source access fails closed.
- Rescans are expected recovery operations, not exceptional migrations.
- Exact timing targets remain to be approved with the first provider.
