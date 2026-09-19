# ADR 0041: Immutable delivery, secrets, and migrations

- Status: Accepted
- Date: 2026-09-13
- Milestone: 8.0–8.1

## Context

Copying a working directory to a VM is not reproducible and risks leaking credentials
or running a database migration from the wrong revision. Phase 8 needs a release unit
that can be verified, promoted, rolled back, and restored.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| SSH and rebuild on the VM | Minimal setup | Non-reproducible artifacts and broad deployment credentials |
| Mutable `latest` images | Simple commands | Ambiguous rollback and supply-chain drift |
| Signed immutable multi-architecture images with an approved deploy job | Reproducible and reviewable | More CI and keyless-signing setup |

## Proposed decision

GitHub Actions builds tested AMD64/ARM64 OCI images identified by digest, emits an SBOM,
scans them, and signs the accepted manifest. Deployment uses an environment approval,
least-privilege short-lived identity where OCI supports it, and no secrets in images or
Git. Runtime secrets come from an ignored bootstrap or OCI secret boundary and are
never printed.

Run Alembic through a single pre-deployment migrator with compatibility checks. A
release cannot switch traffic until migrations, readiness, and smoke checks pass.
Rollback uses the prior image digest and only migration paths explicitly proven safe;
restore is preferred over destructive schema commands.

## Recommendation

Approve digest-pinned, signed delivery with a manual production-learning approval gate.
Do not automate unattended cloud changes while the project has one learning operator.

## Approval questions

1. Approve immutable multi-architecture images, SBOM, scan, and signing gates?
2. Approve a manually authorized deployment job and no long-lived cloud key in Git?
3. Approve a single migration job with compatibility and rollback evidence?

## Consequences

- Deployments become reproducible and auditable.
- Initial delivery setup is larger than copying files to a VM.
- Release rollback cannot depend on an unproven destructive database downgrade.

## Decision record

Accepted by the user on 2026-09-13. Immutable multi-architecture artifacts, protected
secrets, explicit deployment approval, and migration-safe promotion/rollback are binding.
