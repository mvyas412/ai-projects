# ADR 0054: Dependency and supply-chain maintenance

- Status: Accepted
- Date: 2026-09-20
- Milestone: 10.3

## Context

Pinned dependencies, images, SBOMs, scans, and signatures protect reproducibility, but
they also age. Unbounded or unattended upgrades could break ARM64 deployment, model
behavior, migrations, security controls, or protected evaluation evidence.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Update only after failures | Minimal routine work | Long exposure and difficult upgrade jumps |
| Fully automatic dependency updates | Fast patch uptake | Noisy, risky, and may consume paid tests |
| Scheduled grouped candidates with evidence gates | Predictable and reviewable | Requires maintenance automation and triage |

## Decision

Create bounded monthly update candidates grouped by ecosystem. Require lockfile
integrity, source/IaC/image scans, SBOM/provenance checks, deterministic tests, migration
checks, protected free evaluations, ARM64 build validation, and an immutable rollback
manifest. Never auto-merge or run paid acceptance; urgent vulnerabilities use a narrow
reviewed path.

## Accepted defaults

- Produce grouped maintenance candidates monthly; never auto-merge or automatically run
  paid acceptance.
- Use the urgent path for known-exploited vulnerabilities affecting MM-RAG, exploitable
  critical vulnerabilities, or high-severity vulnerabilities with a public exploit in
  an exposed component.
- Require exercised rollback evidence for runtime, database, and container-image
  promotions. Documentation-only and isolated development-tool changes do not require a
  deployment rollback drill.

## Consequences

- Maintenance becomes regular without sacrificing release evidence.
- Human review remains required for promotion and any paid validation.
