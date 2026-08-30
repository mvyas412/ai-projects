# ADR 0003 — Local storage behind an object-storage interface

- **Status:** Accepted
- **Date:** 2026-08-29
- **Phase:** 2.1

## Context

Phase 2 needs a safe local development path while Phase 3 owns durable
S3-compatible object storage and asynchronous ingestion. Application services
must not bake local filesystem paths into product identities or business logic.

## Decision

Use a local file adapter behind an `ObjectStorage` protocol during Phase 2.

- Storage keys are stable POSIX-style relative identifiers, not user filenames.
- Absolute paths, traversal segments, and platform-specific separators are rejected.
- Writes use a temporary file followed by an atomic replacement.
- Runtime data stays under ignored `data/runtime/storage` by default.
- The adapter exposes put, read, exists, and delete operations that an
  S3-compatible Phase 3 adapter can implement.

## Consequences

- Local Phase 2 files are not a production durability mechanism.
- Database records should store object keys and version IDs, never absolute paths.
- Phase 3 can replace the adapter without changing application-service contracts.
- Backup, retention, signed URLs, encryption policy, and lifecycle controls remain
  Phase 3/4 work.
