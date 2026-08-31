# ADR 0013: Central RBAC and resource ACL policy

- Status: Proposed
- Date: 2026-08-31
- Milestone: 4.0–4.1

## Context

ADRs 0001–0006 establish authenticated users, four workspace roles, tenant-scoped
resources, backend-mediated retrieval, and append-only activity. Phase 3 preserves
those checks while adding jobs, workers, vectors, and object storage. Authorization
is currently distributed across services as membership checks and role sets, which
makes a fine-grained rule difficult to review and easy to apply inconsistently.

Phase 4 needs one understandable policy contract that can govern SQL, vectors,
objects, jobs, conversations, citations, and administrative actions without making
the frontend or an external policy product authoritative.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Keep role checks in each service | Smallest immediate change | Rules drift, poor audit explanation, and omissions become likely as resources grow |
| Workspace RBAC only | Simple and compatible | Cannot protect private conversations or restricted document/collection sets |
| Per-resource ACLs only | Very flexible | Duplicates workspace administration, creates large ACL sets, and obscures role ceilings |
| Central RBAC ceiling plus optional resource ACL grants | Preserves current roles, supports restricted resources, and yields one testable decision path | Requires policy vocabulary, ACL persistence, list filtering, migration defaults, and cache discipline |
| External policy engine now | Rich policy language and centralized evaluation | New service/runtime, policy deployment, availability, and debugging complexity before scale requires it |

## Proposed decision

Use a central in-process policy service with stable action/resource codes. Preserve
the accepted `owner`, `admin`, `member`, and `viewer` roles as maximum capability
ceilings. Add optional user-level ACL grants for resources marked `restricted`.

The complete proposed matrix and inheritance rules are defined in
[`PHASE4_POLICY_THREAT_MODEL.md`](../PHASE4_POLICY_THREAT_MODEL.md).

### Core semantics

- Deny by default. Unknown action, resource, role, visibility, or ACL revision denies.
- Current workspace membership is mandatory. ACLs cannot cross a workspace or
  elevate a caller above their workspace role.
- `workspace` resources inherit role access. `restricted` resources require
  owner/admin authority, creator authority, or an explicit in-workspace user grant.
- The first revision uses positive user grants only. Removing a grant denies access.
  Explicit denies, group principals, external principals, and public links are deferred.
- Owner/admin retain the content-administration scope accepted by ADR 0002. Only
  owner may transfer ownership, delete a workspace, or approve irreversible purge.
- Existing resources migrate as workspace-visible. New documents and collections
  remain workspace-visible. New conversations are recommended to be creator-private.
- Child resources inherit policy: versions, generations, objects, vectors, citations,
  and jobs inherit their document; messages inherit their conversation.
- Collection access never grants document access. Retrieval uses the intersection
  of readable collection members and current authorized document scope.
- Unauthorized discovery returns 404; a visible resource with a disallowed action
  returns 403. List endpoints filter before serialization.

### Policy-service boundary

The application asks one service for a decision using trusted principal, workspace,
action, resource identity/type, and lifecycle context. The service returns only a
typed allow/deny result and resolved scope; routes do not interpret roles themselves.
Repositories receive trusted scope from application services and remain unable to
construct authorization from request body fields.

Policy decisions are request-scoped and initially uncached. A cache may be added
only with a bounded expiry, membership/ACL revision invalidation, and revocation
tests. Frontend visibility mirrors policy for usability but never grants access.

## Consequences

- One matrix can be reviewed, tested, audited, and versioned.
- Existing document and collection behavior remains compatible while restricted
  resources can be introduced deliberately.
- Conversation privacy improves for newly created conversations after implementation.
- Every service and list query must migrate away from local role sets.
- User-only positive grants are intentionally less expressive than enterprise ACLs.
- Admin content access is powerful and therefore requires immutable attribution.

## Approval points

The recommendation requests approval for these first-revision defaults:

1. existing resources remain workspace-visible;
2. new conversations default to restricted/creator-managed;
3. ACLs use positive in-workspace user grants only;
4. owner/admin can administer all workspace content;
5. ACLs never override membership or a role ceiling; and
6. accepted jobs become workspace-owned even if the requester later loses membership.

## Acceptance evidence required

- Exhaustive table-driven tests cover every role/action/resource matrix entry.
- Unknown and malformed policy inputs fail closed.
- Cross-workspace ACL creation and use are rejected by application and database constraints.
- List, detail, mutation, job, retrieval, citation, and download paths use the same policy.
- Role/ACL removal prevents subsequent access without waiting for a process restart.
- Existing-resource migration preserves current visibility.
- Public errors and audit payloads contain no secret, token, raw content, or object coordinate.
