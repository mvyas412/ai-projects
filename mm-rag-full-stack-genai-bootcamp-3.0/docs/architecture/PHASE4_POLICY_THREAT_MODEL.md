# Phase 4 policy matrix and threat model

> Milestone 4.0 decision package — Proposed 2026-08-31

This document defines the proposed authorization vocabulary, first public policy
matrix, trust boundaries, and threat-model changes for Phase 4. It is a review
artifact, not implementation evidence. Existing Phase 3 behavior remains unchanged
until the corresponding ADRs are accepted and each enforcement slice is tested.

## Goals and invariants

- FastAPI is the only public authorization boundary.
- Auth0 proves identity; PostgreSQL resolves current workspace membership, role,
  resource visibility, and ACL grants.
- Every decision is default-deny and uses server-resolved actor, action, resource,
  workspace, and policy version.
- Workspace membership is always required. An ACL can never share a resource across
  workspaces or grant more capability than the member's workspace role allows.
- Owner and admin retain workspace-wide content administration. Only owners may
  transfer ownership, delete a workspace, or approve irreversible workspace purge.
- SQL, Qdrant, object, job, conversation, citation, and audit access apply the same
  policy outcome. A frontend control is never enforcement.
- Unauthorized resource lookup stays non-enumerating. Existing 404 behavior is
  preserved when the caller cannot discover the resource; 403 is used only when
  the resource is visible but the requested action is forbidden.
- Tokens, credentials, raw document or message content, object coordinates, and raw
  dependency errors never enter policy, audit, broker, or public-error payloads.

## Proposed policy representation

The central policy service evaluates this tuple:

```text
principal + workspace membership + action + resource + resource visibility/ACL
          + current lifecycle state + trusted request context
```

The existing roles remain stable:

| Role | Maximum capability |
| --- | --- |
| `owner` | Workspace ownership, members, policy, lifecycle, and all content |
| `admin` | Members, policy, settings, and all content except ownership transfer and workspace purge |
| `member` | Create content and work with content visible or granted to them |
| `viewer` | Read and chat with content visible or granted to them; no content mutation |

Resources have one of two visibility modes:

| Mode | Discoverability |
| --- | --- |
| `workspace` | Every current workspace member may discover the resource, subject to role action limits |
| `restricted` | Owner/admin, creator, and explicitly granted in-workspace users may discover it |

The first ACL revision supports user principals only and positive grants only.
Removing a grant denies access; explicit deny rows, groups, external principals,
cross-workspace sharing, public links, and source-system ACL propagation are not in
the first implementation. This keeps precedence deterministic and leaves group and
connector mapping for a later reviewed extension.

Existing documents, collections, and conversations migrate as `workspace` to avoid
silent loss of access. New documents and collections remain `workspace` by default.
The recommendation is for new conversations to default to `restricted`, with the
creator receiving `manage`; this protects question and answer history while still
allowing deliberate sharing.

## Action and resource matrix

Legend: **All** means role-wide access in the workspace; **Allowed** means the role
may perform the action when the resource is visible; **Own/granted** applies the
resource ACL or requester rule; **No** is denied.

| Resource and action | Owner | Admin | Member | Viewer |
| --- | --- | --- | --- | --- |
| Workspace: view | All | All | All | All |
| Workspace: change settings | All | All | No | No |
| Workspace: invite/remove members and change non-owner roles | All | All | No | No |
| Workspace: transfer ownership or request workspace purge | All | No | No | No |
| Policy/ACL: inspect | All | All | Own/granted | Own/granted |
| Document/collection ACL: change visibility or grants | All | All | Own | No |
| Conversation ACL: change visibility or grants | All | All | Own | Own |
| Document: list/read/download | All | All | Visible/granted | Visible/granted |
| Document: upload or add version | All | All | Allowed | No |
| Document: index/reprocess | All | All | Visible/granted | No |
| Document: archive/restore | All | All | No | No |
| Document: request permanent purge | All | No | No | No |
| Collection: list/read | All | All | Visible/granted | Visible/granted |
| Collection: create or change document membership | All | All | Visible/granted | No |
| Collection: archive/restore | All | All | No | No |
| Conversation: create | Allowed | Allowed | Allowed | Allowed |
| Conversation: read/chat/export | All | All | Own/granted | Own/granted |
| Conversation: rename/delete/share | All | All | Own | Own |
| Ingestion job: list/read | All | All | Inherited document access | Inherited document access |
| Ingestion job: cancel/retry | All | All | Own request + inherited document access | No |
| Safe workspace activity: read | All | All | Allowed | Allowed |
| Security audit and compliance export: read/create | All | All | No | No |
| Retention candidates: preview | All | All | No | No |
| Irreversible retention/deletion: approve/apply | All | No | No | No |

The matrix is a policy source, not route-specific code. Endpoints and workers must
request stable action codes such as `document.read`, `document.version.create`,
`conversation.message.create`, `job.cancel`, `acl.update`, or `retention.apply`.
Unknown action/resource combinations deny by default.

## Inheritance and composition rules

- Document versions, generations, source objects, vector points, citations, and
  ingestion jobs inherit their document's visibility. They do not carry independent
  user ACLs in the first revision.
- A collection ACL controls discovery and use of the collection, but membership in
  that collection never grants access to a restricted document. Authorized query
  scope is the intersection of collection contents and independently readable
  documents.
- A conversation ACL controls the conversation history. Every message request
  re-resolves authorization for each target document before retrieval and again
  before citation persistence. Sharing a conversation does not share its sources.
- Owner/admin content administration is explicit in the role contract and audited.
  It is not modeled as a hidden ACL row.
- Role downgrade, member removal, resource restriction, and ACL removal affect new
  API reads immediately. Already authorized ingestion becomes workspace-owned and
  may finish, but a deletion/cancellation tombstone wins before promotion. Current
  policy governs who can see the result.

## Trust boundaries

| Boundary | Untrusted input | Required control |
| --- | --- | --- |
| Browser to FastAPI | Token, path IDs, action parameters, filenames | Strict JWT validation, current membership lookup, typed action policy, safe validation |
| FastAPI to PostgreSQL | Application query and pooled connection state | Central policy before query plus transaction-local RLS context and non-bypass runtime role |
| FastAPI/worker to Qdrant | Requested scope and returned payload | Trusted filter builder, authorized document set, workspace/version/generation predicates, post-retrieval validation |
| FastAPI/worker to object storage | Object reference and download request | Resolve reference from authorized SQL row; private buckets; no client-selected key |
| Outbox/RabbitMQ to worker | Event and job ID | Strict schema; reload PostgreSQL truth; fenced claim; message is never authorization |
| Model to persistence | Answer and citations | Treat output as untrusted; validate every citation against current authorized scope |
| Audit/export to administrator | Filters and exported fields | Admin policy, bounded queries, safe schema, no content or credentials, immutable export evidence |
| Retention worker to stores | Candidate identifiers | Tombstone, durable plan, recheck under policy/state, idempotent deletion, reconciliation |

## Threat model

| Threat | Example | Proposed mitigation and evidence |
| --- | --- | --- |
| Cross-tenant IDOR/enumeration | An outsider guesses a workspace, document, job, or conversation UUID | Membership and resource policy before lookup; tenant predicates/RLS; non-enumerating 404; negative API and live-PostgreSQL tests |
| Horizontal access inside a workspace | A member opens a restricted document or another user's private conversation | Resource visibility plus ACL check; inherited child-resource policy; list filtering; matrix tests for every role |
| Vertical privilege escalation | A member submits `admin`, changes an ACL, exports audit, or applies retention | Roles loaded only from PostgreSQL; stable action codes; owner-only boundaries; mutation audit; forbidden-action tests |
| Missing SQL tenant predicate | A repository method omits `workspace_id` | PostgreSQL RLS defense, composite tenant foreign keys, non-bypass roles, schema-policy drift tests |
| Stale pooled database context | One request inherits another tenant's session setting | `SET LOCAL` inside every transaction, pool reset, no session-global policy variables, cross-request concurrency tests |
| Qdrant filter omission or broadening | Retrieval searches every tenant or ignores a restricted document | One trusted policy-aware filter builder; mandatory workspace/document/version/generation clauses; fail-closed tests and post-result validation |
| Object-key or signed-link abuse | Caller supplies another tenant's key or replays a leaked link | Keys never accepted from clients; SQL authorization before resolution; short-lived audience/action-bound capability if signed access is later enabled |
| Broker/worker confused deputy | Forged or stale message names another tenant's job | Minimal message; PostgreSQL reload; scoped system role; fencing, lifecycle, and current tombstone checks |
| Citation data leak | Model returns evidence outside the authorized set | Revalidate source IDs and active generations before persistence and response; reject the answer on mismatch |
| Permission change race | Access is revoked while a chat, export, or download is running | Resolve at request start and recheck before durable/high-risk completion; short expiries; deterministic revocation-race tests |
| Audit suppression or disclosure | Mutation commits without evidence, or audit stores content/token data | Same-transaction audit for privileged mutations; strict safe field schema; append-only DB permissions; payload tests |
| Partial deletion/orphaned evidence | SQL is deleted while vectors or objects remain searchable | Tombstone first; durable deletion plan; deny reads immediately; idempotent cross-store purge and reconciliation before completion |
| Admin misuse | An admin reads or exports sensitive workspace content | Explicit admin capability, immutable attribution, least-privilege export, no hidden impersonation, owner-visible security activity |
| Denial-of-service through denied requests | Attacker floods audit with guessed IDs | Rate limiting later at gateway, bounded denial events, stable metadata only, operational aggregation without weakening denial |

## Proposed Phase 4 decision and delivery sequence

1. ADR 0013 — central RBAC/ACL representation and policy semantics.
2. ADR 0014 — PostgreSQL RLS roles, transaction context, and worker boundaries.
3. ADR 0015 — Qdrant, object access, async-work, and connector-permission contract.
4. ADR 0016 — append-only security audit and compliance export contract.
5. ADR 0017 — retention, deletion, encryption, and incident-response contract.
6. After acceptance, implement Milestones 4.1–4.5 as small vertical slices with
   deterministic and live cross-tenant tests before any Phase 4 release claim.

## Approval questions and recommendations

| Question | Recommendation |
| --- | --- |
| Should existing resources become restricted during migration? | No. Preserve them as workspace-visible; restriction is an explicit later action. |
| Should new conversations be private? | Yes. Default new conversations to restricted and creator-managed. |
| Can an ACL grant access outside the workspace or above a role's ceiling? | No. Membership and role ceiling always apply. |
| Should the first ACL support groups or explicit deny rows? | No. Begin with positive user grants; add groups/source ACLs through a later ADR. |
| Can admins access restricted content? | Yes, under the existing content-administration role, with immutable audit attribution. |
| Does member removal cancel their already accepted ingestion jobs? | No. The job is workspace-owned after acceptance; deletion/cancellation state can still stop promotion. |
| Should provider-direct presigned URLs be introduced now? | No. Keep backend-mediated downloads; approve a short-lived capability contract only when scale requires it. |
