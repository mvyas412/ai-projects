# ADR 0052: Automated backup verification and isolated restore drills

- Status: Accepted
- Date: 2026-09-20
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

## Decision

Use the existing encrypted, checksummed backup format. Separate frequent backup and
integrity checks from less frequent isolated restore drills. Restore only into disposable,
network-restricted resources; validate schema head, aggregate counts, vector health,
object checksums, and application readiness. Publish only content-free evidence. Never
overwrite the active data plane during a drill.

## Accepted defaults

- Run one encrypted backup and integrity verification daily.
- Run one isolated restore drill monthly.
- Retain seven daily and two monthly known-good generations subject to measured free
  storage capacity, and never delete the final two known-good generations.
- Keep the existing private OCI bucket as the only cloud destination.
- A restore drill never overwrites the active data plane.

## Consequences

- Recovery failures become visible before an incident.
- Automation needs leases, bounded runtime, safe cleanup, and missed-run alerts.
