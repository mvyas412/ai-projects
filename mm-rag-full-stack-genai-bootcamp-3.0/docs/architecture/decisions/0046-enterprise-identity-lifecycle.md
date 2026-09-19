# ADR 0046: Enterprise identity lifecycle and group mapping

- Status: Proposed
- Date: 2026-09-19
- Milestone: 9.3

## Context

OIDC sign-in exists, but enterprise lifecycle also needs deterministic provisioning,
group changes, suspension, and deprovisioning. Identity-provider roles must not bypass
workspace policy or become an uncontrolled authorization source.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Just-in-time login only | Minimal integration | Weak offboarding and group lifecycle |
| Provider-specific management API | Fast for one vendor | Lock-in and inconsistent semantics |
| SCIM-compatible adapter plus OIDC federation | Standard lifecycle boundary | Mapping and reconciliation complexity |

## Proposed decision

Retain OIDC for authentication and add a SCIM-compatible provisioning adapter for users
and groups. Store external identities and groups as tenant-scoped mappings to stable
internal IDs. Group mapping grants only pre-approved product roles or positive ACLs and
never exceeds the central RBAC ceiling. Deactivation immediately blocks new sessions and
access; durable work follows the accepted safe-finish/cancel policy. Provisioning events
are idempotent, ordered per tenant, audited without sensitive claims, and reconciled.

No identity or SCIM provider is selected by this ADR.

## Recommendation

Approve standards-first OIDC plus SCIM, with explicit group mapping and deny-first
deprovisioning.

## Approval questions

1. Approve SCIM-compatible provisioning behind an adapter?
2. Approve explicit allowlisted group-to-role mappings only?
3. Approve immediate access denial on suspension/deprovisioning?

## Consequences

- Existing Auth0 login can remain while lifecycle providers stay replaceable.
- Group mappings require administrative review and reconciliation evidence.
- Provider choice and external tenant configuration remain separate approvals.
