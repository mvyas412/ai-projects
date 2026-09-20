# ADR 0052: Automated backup verification and isolated restore drills

- Status: Proposed
- Date: 2026-09-19
- Milestone: 10.1

## Context

Phase 8 proved one encrypted backup and restore. A durable operational posture needs
freshness, integrity, and restorability checked repeatedly without exposing plaintext
or turning a successful upload into false confidence.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Manual backups only | Simple | Easy to forget; restore quality decays silently |
| Verify checksums only | Cheap and fast | Does not prove PostgreSQL, Qdrant, or object restoration |
| Scheduled encrypted backup plus isolated restore drills | Proves usable recovery | More runtime and storage management |

## Proposed decision

Use the existing encrypted, checksummed backup format. Separate frequent backup and
integrity checks from less frequent isolated restore drills. Restore only into disposable,
network-restricted resources; validate schema head, aggregate counts, vector health,
object checksums, and application readiness. Publish only content-free evidence. Never
overwrite the active data plane during a drill.

## Recommendation

Run daily encrypted backups with local verification and a monthly isolated restore drill,
subject to free storage and runtime limits. Retain at least the newest known-good backup
and one prior generation; exact retention remains an approval question.

## Approval questions

1. Approve daily verification and monthly isolated restore as the initial cadence?
2. What encrypted backup generations should be retained within the free budget?
3. Should the existing private OCI bucket remain the only cloud destination?

## Consequences

- Recovery failures become visible before an incident.
- Automation needs leases, bounded runtime, safe cleanup, and missed-run alerts.
