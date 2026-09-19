# ADR 0043: Phase 9 enterprise scope and trust boundaries

- Status: Accepted
- Date: 2026-09-19
- Milestone: 9.0

## Context

Phase 9 adds enterprise content, identity lifecycle, commercial controls, and
compliance administration. These capabilities introduce privileged integrations and
new cross-system consistency risks, but the learning deployment must remain free-first
and preserve the accepted tenant and authorization boundaries.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Select vendors first | Fast demos | Provider behavior defines the architecture and increases lock-in |
| Build all enterprise features together | One broad delivery | Large blast radius and weak review boundaries |
| Provider-neutral contracts in milestone order | Reviewable and portable | More decision work before implementation |

## Proposed decision

Keep FastAPI as the authorization authority and PostgreSQL as relational truth. Add
Phase 9 through adapters and durable records inside the modular monolith unless measured
load or isolation evidence justifies a service split. Sequence work as connectors and
sync, identity lifecycle, usage controls, billing, then compliance. Each integration
must be tenant-scoped, least-privilege, revocable, idempotent, observable, and fail
closed without exposing source or billing details.

Use synthetic or non-sensitive learning data. Keep the OCI USD 0 target and require
separate approval for any paid plan, provider account, credential, external write, or
paid acceptance run. Provider selection is not part of this ADR.

## Recommendation

Approve the provider-neutral, milestone-gated approach and retain the modular monolith.

## Approval questions

1. Approve the ordered Phase 9 scope and trust boundaries?
2. Keep provider choices and paid resources behind separate decisions?
3. Require evidence for tenant isolation, revocation, concurrency, and reconciliation?

## Consequences

- Phase 9 can start without prematurely selecting vendors.
- Every later ADR must preserve existing authorization and audit invariants.
- Implementation remains blocked until the relevant ADR is accepted.

## Decision record

Accepted by the user on 2026-09-19. The provider-neutral milestone order, existing
trust boundaries, modular-monolith default, free-first guardrail, and separate approval
for provider-specific or paid activity are binding.
