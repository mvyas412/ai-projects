# ADR 0004: Workspace-scoped document library and vector identity

- Status: Accepted
- Date: 2026-08-30
- Milestone: 2.2

## Context

Phase 2 needs persistent multi-document metadata, immutable versions, collections,
and retrieval scope without introducing the Phase 3 worker and object-storage
systems prematurely. Every data access path must prevent cross-workspace discovery.

## Decision

1. A workspace is the Phase 2 tenant boundary. SQL resources carry
   `workspace_id`; Qdrant payloads carry both `tenant_id` and `workspace_id`, with
   the same value until a distinct organization boundary is introduced.
2. `documents` represent stable logical identity. `document_versions` are
   immutable content/config identities using SHA-256 content and ingestion
   fingerprints plus monotonically increasing version numbers.
3. Composite foreign keys require collection memberships and document versions
   to use the same workspace as their parent resources.
4. Repository queries receive workspace identity from authenticated backend
   context. Client-supplied workspace identity is never used without membership
   verification, and unauthorized lookups return 404.
5. Owner, admin, and member roles may upload/version/organize documents. Only
   owner and admin roles may archive. Viewers remain read-only.
6. Phase 2 stores binaries through the existing path-safe local `ObjectStorage`
   adapter. Database failure triggers compensating object deletion. Phase 3 will
   replace the adapter without changing document identity.
7. Every vector payload must contain keyword-indexed `tenant_id`, `workspace_id`,
   `document_id`, and `document_version_id`. Filters are constructed by trusted
   backend helpers rather than request payloads.

## Consequences

- Tenant consistency is enforced in both application code and relational
  constraints.
- Duplicate content/config versions are rejected deterministically.
- Archiving is non-destructive, preserving auditability and future reprocessing.
- Local storage is suitable for Phase 2 demonstrations but not durable or
  independently scalable; that limitation is explicitly deferred to Phase 3.
