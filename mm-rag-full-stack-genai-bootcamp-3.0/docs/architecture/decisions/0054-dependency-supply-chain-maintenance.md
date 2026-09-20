# ADR 0054: Dependency and supply-chain maintenance

- Status: Proposed
- Date: 2026-09-19
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

## Proposed decision

Create bounded monthly update candidates grouped by ecosystem. Require lockfile
integrity, source/IaC/image scans, SBOM/provenance checks, deterministic tests, migration
checks, protected free evaluations, ARM64 build validation, and an immutable rollback
manifest. Never auto-merge or run paid acceptance; urgent vulnerabilities use a narrow
reviewed path.

## Recommendation

Adopt monthly grouped candidates plus a separately approved urgent-security path.

## Approval questions

1. Approve monthly grouped maintenance candidates?
2. Which severity and exploitability threshold triggers the urgent path?
3. Require an exercised rollback before promoting every runtime/image update?

## Consequences

- Maintenance becomes regular without sacrificing release evidence.
- Human review remains required for promotion and any paid validation.
