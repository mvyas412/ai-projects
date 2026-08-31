# ADR 0015: Authorized vector, object, and asynchronous access

- Status: Accepted
- Date: 2026-08-31
- Milestone: 4.0–4.3

## Context

PostgreSQL can resolve current membership and ACL state, but Qdrant, SeaweedFS/S3,
RabbitMQ, and long-running ingestion do not enforce product policy themselves.
Phase 4 must prevent a policy decision from being weakened as data crosses those
boundaries. The future connector contract must also have a fail-closed place to
carry source permissions without selecting a connector in Phase 4.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Copy user ACL arrays into every vector/object | Fast provider-side filtering | Stale grants, expensive fan-out on role changes, and provider-specific ACL logic |
| Trust client filters, object keys, or broker claims | Simple request handling | Critical confused-deputy and cross-tenant exposure risk |
| Resolve policy in PostgreSQL and compile bounded provider scope | Current policy remains authoritative and provider-neutral | Adds authorization lookups and bounded-scope handling |
| Issue provider-direct presigned URLs immediately | Reduces API download traffic | Leaks provider coordinates, complicates revocation, and expands replay risk before scale requires it |

## Decision

Resolve authorization in PostgreSQL through ADR 0013, then compile the smallest
trusted scope needed by each provider. Provider metadata supports validation but is
never an independent authorization source.

### Qdrant

- Clients never submit payload filters.
- The backend resolves readable document/version/generation identities and builds
  mandatory workspace, document, version, generation, and vector-kind predicates.
- A restricted collection query intersects collection membership with readable
  documents before search. An empty intersection returns no evidence.
- Returned vectors and model citations are revalidated against the resolved set.
- The first implementation uses bounded explicit document identities. A materialized
  ACL revision or provider-side principal index requires a later performance ADR.

### Object storage and downloads

- Buckets remain private and keys remain server-generated opaque references.
- The default download continues through the authorized FastAPI boundary. The
  browser never supplies or receives a trusted bucket/key pair.
- Provider-direct presigned URLs remain deferred. If scale later requires signed
  access, first introduce a short-lived application capability bound to principal,
  workspace, resource/version, action, audience, policy revision, and expiry; redeeming
  it rechecks current policy before returning bytes or a tightly bounded provider URL.
- Delete capability is never issued to a browser.

### Asynchronous work

- Broker messages remain untrusted wake-up hints under ADRs 0009–0012.
- A worker reloads the job and uses its trusted workspace/document/version scope.
- Once intake commits, the job is workspace-owned and may finish after requester
  membership removal. Removal immediately blocks that user from status and output.
- A current resource tombstone, authorized cancellation, or lifecycle deletion wins
  before promotion. Workers recheck those conditions at safe checkpoints.

### Future connector permission envelope

No connector is selected or implemented in Phase 4. The contract reserves a
versioned source principal/ACL snapshot linked to connector, source item, sync
revision, workspace resource, and last verification time. Unknown principals,
stale mandatory permission data, or unsupported ACL semantics fail closed. Mapping
enterprise groups and propagating source changes remain Phase 9 work.

## Consequences

- Revocation stays authoritative in PostgreSQL instead of waiting for vector/object rewrites.
- Large authorized document sets may require later evaluated optimization.
- Backend-mediated downloads remain simpler and safer but consume API bandwidth.
- In-flight ingestion is operationally stable while requester access changes immediately.
- Connectors have a secure extension point without expanding Phase 4 scope.

## Acceptance resolution

The review accepted on 2026-08-31 backend-streamed downloads, treating
accepted jobs as workspace-owned, and deferring direct presigning and connector/group
implementation until measured need and later ADRs.

## Acceptance evidence required

- Omitting any required Qdrant scope field fails before search.
- Restricted collection, conversation, and citation tests cannot use unreadable documents.
- Client-supplied filters and object keys are rejected or ignored as authorization evidence.
- Member removal blocks subsequent reads while an accepted job remains safely recoverable.
- Tombstone/cancellation races cannot promote deleted or cancelled content.
- Cross-workspace object and vector attempts fail in deterministic and live-provider tests.
- No public error, link, log, or audit event discloses credentials or unrestricted object coordinates.

## Milestone 4.2 implementation evidence

Qdrant retrieval now rejects empty, incomplete, oversized, or generation-less scope
before provider access and intersects mandatory tenant, workspace, document, version,
generation, and vector-kind predicates. Returned payloads are independently checked
against that trusted scope before citation use. Deterministic negative tests and a
live two-tenant Qdrant test pass.

Milestone 4.3 adds one canonical original-object resolver for API downloads,
synchronous indexing, and workers. Provider access verifies the trusted tenant,
document, version, server-generated key, byte count, media type, and checksum before
use; downloads stream through FastAPI and never accept or disclose provider keys.

Migration `20260831_0011` adds versioned source permission snapshots linked to an
immutable document version. It stores a hashed source-item reference, source/sync/
permission revisions, resolved internal user principals, verification/expiry, and a
canonical fingerprint. Unsupported semantics, unresolved principals, non-members,
stale evidence, tampering, and cross-workspace RLS access fail closed. No connector,
group mapper, direct presigning, or provider-specific ACL engine was selected.
