# ADR 0044: Connector SDK and credential envelope

- Status: Accepted
- Date: 2026-09-19
- Milestone: 9.0–9.1

## Context

Enterprise sources differ in authentication, pagination, permissions, rate limits,
change tracking, and deletion behavior. A provider-specific first implementation would
make those differences leak into ingestion and authorization.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Provider code in ingestion | Small first change | Tight coupling and inconsistent security |
| Third-party connector platform | Broad catalog | Cost, data exposure, and vendor dependency |
| Internal provider-neutral SDK | Controlled contract and portable tests | Adapter work per source |

## Proposed decision

Define a connector SDK for discovery, content streaming, checkpointed change listing,
permission snapshots, deletion signals, health, and rate-limit hints. Connectors return
canonical records; they never write directly to product stores or decide product access.
Credentials use opaque tenant-scoped references resolved only at execution time, with
minimum scopes, rotation/revocation metadata, redacted telemetry, and no secret values
in jobs, logs, evidence, or Git.

Choose the first source only after scoring demand, free learning access, permission and
deletion fidelity, webhook/delta support, testability, and operational burden. No source
provider is selected here.

## Recommendation

Approve the internal SDK and credential envelope, then compare Google Drive,
Microsoft SharePoint/OneDrive, Box, and a generic authenticated web/API adapter using
the same scorecard before selecting one.

## Approval questions

1. Approve the canonical connector interface and runtime-only credential resolution?
2. Approve the proposed provider scorecard?
3. Which first source best matches the intended learning scenario?

## Consequences

- Provider quirks stay behind adapters.
- A credential-vault implementation remains a separate deployment decision.
- Connector implementation waits for first-source approval.

## Decision record

Accepted by the user on 2026-09-19. The provider-neutral SDK, runtime-only opaque
credential references, and provider scorecard are approved. The first source remains
TBD and requires a separate selection.
