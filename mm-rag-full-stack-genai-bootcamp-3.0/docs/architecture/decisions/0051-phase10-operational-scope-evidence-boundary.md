# ADR 0051: Phase 10 operational scope and evidence boundary

- Status: Accepted
- Date: 2026-09-20
- Milestone: 10.0

## Context

Phases 1–9 produced an accepted learning platform, but routine maintenance, recovery,
retention scheduling, and upgrade operations are not yet one governed program. Adding
automation without a shared boundary could create destructive, privacy, cost, or
availability risk.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Stop at Phase 9 | No new complexity | Operational knowledge remains manual and fragile |
| Automate each task independently | Fast local improvements | Inconsistent evidence, authority, and rollback behavior |
| One evidence-gated operational phase | Shared safety model and review order | More decision work before automation |

## Decision

Define Phase 10 as operational hardening around the existing modular-monolith and OCI
learning deployment. Require plan/authorize/execute/verify/rollback stages, content-free
evidence, stable scope, free-first limits, and explicit approval for destructive,
provider-specific, credential, or paid actions. Do not change product authorization,
data ownership, retrieval defaults, or accepted release tags.

## Accepted defaults

- Phase 10 is operational hardening, not a new product capability.
- The approximate ten-user and USD 0 learning targets remain binding.
- Every operational change requires content-free evidence and a reviewed rollback or
  restore path.
- Destructive, provider-specific, credential, paid, and cloud-resource actions remain
  separate approval boundaries.

## Consequences

- Later operational ADRs share one trust and evidence model.
- No Phase 10 implementation is authorized until its relevant ADR is accepted.
