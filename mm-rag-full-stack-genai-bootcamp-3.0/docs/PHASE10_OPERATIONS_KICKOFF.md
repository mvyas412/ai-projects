# Phase 10 operational-hardening kickoff

> Status: Proposed — decision work only

## Objective

Make the accepted free-first learning deployment easier to maintain, recover, upgrade,
and eventually retire without weakening authorization, tenant isolation, immutable
provenance, citation validation, privacy, or cost controls.

Phase 10 is not a production-SLA claim. It adds repeatable operational evidence around
the existing product and OCI deployment. No new provider, paid capacity, automatic
retention, unattended upgrade, or destructive schedule is selected by this kickoff.

## Binding invariants

- FastAPI remains the authorization authority; operational tools never bypass product
  policy or PostgreSQL RLS.
- PostgreSQL, Qdrant, and object-storage identities remain stable and versioned.
- Maintenance and recovery evidence is aggregate/content-free and contains no secrets,
  provider identifiers, private URLs, customer content, or access tokens.
- Every destructive or replacement operation starts with an exact reviewed plan and
  fails closed if scope, authorization, hold state, or expected revision changes.
- The learning target remains approximately ten users and USD 0 infrastructure spend.
- Paid services, larger OCI shapes, new credentials, and paid model calls require
  separate explicit approval.
- Phase 5 defaults and rollback profiles remain unchanged.

## Proposed milestone sequence

1. Define operational scope, evidence, and failure budgets.
2. Automate encrypted backup verification and isolated restore drills.
3. Decide whether and how retention may be scheduled; keep it disabled meanwhile.
4. Add bounded dependency, vulnerability, and image-maintenance gates.
5. Add OCI saturation, certificate, backup-age, and budget guardrails.
6. Automate reviewed upgrade, rollback, clean-host recovery, and operator evidence.
7. Publish a complete operator handbook and release proof.

## Threat and control matrix

| Threat | Required control | Acceptance evidence |
| --- | --- | --- |
| Backup exists but cannot restore | Safe extraction, checksums, isolated restore, post-restore integrity probes | Repeatable restore report with RTO/RPO and no content |
| Scheduled deletion removes active/held data | Stable-scope preview, reauthorization, hold precedence, checkpoints, recovery window | Dry-run and synthetic held-data proof before enablement |
| Dependency update breaks security or RAG quality | Pinned inputs, SBOM/scan, deterministic and evaluation gates, rollback manifest | Failed-candidate rejection and successful rollback drill |
| Free OCI host saturates or fills its disk | Capacity thresholds, backpressure, disk/certificate/backup-age alerts, runbook | Ten-user bounded-load and controlled saturation evidence |
| Cost or paid resource appears silently | Budget alerts, inventory allowlist, plan review, no auto-scale | Zero-cost inventory and budget-alarm proof |
| Upgrade or host loss causes data loss | Quiesced backup boundary, immutable release manifest, clean-host restore, rollback | Exercised upgrade/rollback and clean-host recovery |
| Automation leaks secrets or identifiers | Runtime-only credential resolution, redaction, mode-0600 private evidence | Secret scan and content-free evidence validation |

## Decisions requiring approval

- ADR 0051: overall scope, evidence, and non-goals.
- ADR 0052: backup cadence, restore cadence, destinations, and evidence retention.
- ADR 0053: retention schedule, recovery window, exemptions, and authorization model.
- ADR 0054: maintenance cadence, update grouping, vulnerability policy, and rollback gate.
- ADR 0055: capacity thresholds, alert channels, and free-budget controls.
- ADR 0056: upgrade/rollback/DR orchestration and clean-host recovery authority.

Implementation begins only after the applicable ADR is Accepted.
