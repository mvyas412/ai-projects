# ADR 0008: Ingestion idempotency and immutable output promotion

- Status: Accepted
- Date: 2026-08-30
- Milestone: 3.0

## Context

ADR 0004 established immutable document versions using content SHA-256 and an
ingestion fingerprint. Phase 2 still performs synchronous indexing and replaces
vectors in place. The current path can delete an existing index before its
replacement succeeds, and its fingerprint does not yet describe the complete
parser, chunker, embedding, enrichment, and vector-schema configuration.

Phase 3 will use at-least-once wake-up delivery and retryable workers. Duplicate API
requests, duplicate messages, worker crashes, and partial object/vector writes are
therefore normal conditions. The design must prevent duplicate document versions,
jobs, chunks, objects, and vector points while keeping the last validated result
queryable until a replacement is complete.

## Decision drivers

- Preserve stable document/version identity from ADR 0004.
- Make repeated requests and repeated deliveries converge on one logical result.
- Never expose partially written output to retrieval.
- Never delete the active generation before a replacement is validated.
- Keep PostgreSQL authoritative for which generation is visible.
- Support provider-neutral S3-compatible storage and Qdrant without a distributed transaction.
- Make abandoned outputs discoverable for bounded, auditable garbage collection.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Best-effort cleanup after random writes | Minimal identity design | Crashes leave ambiguous duplicates; cleanup cannot prove which result is active |
| Rely on broker deduplication | Reduces some duplicate deliveries | Does not cover API retries, lease expiry, partial writes, or broker retention windows |
| Deterministic IDs with in-place overwrite | Duplicate writes converge | A failed replacement can mix old/new output or make the current index unavailable |
| Deterministic logical identities plus attempt-scoped immutable generations and PostgreSQL promotion | Handles every retry boundary and preserves the prior ready result | Requires generation-aware queries, manifests, validation, and garbage collection |

## Decision

Use layered idempotency and immutable, attempt-scoped output generations. Promote a
validated generation by changing PostgreSQL metadata in one fenced transaction.
PostgreSQL's active-generation pointer is the visibility boundary; future storage
and queue implementations must conform to this contract.

### Acceptance resolution on 2026-08-30

The review accepted these initial policies:

- asynchronous ingestion requires a stable `Idempotency-Key`, generated and
  retained by the client before it submits the request;
- a materially changed pipeline manifest creates a new immutable document version;
- retries and explicit repairs may create new output generations for the same
  version without changing its content/config identity;
- PostgreSQL's active-generation pointer plus mandatory Qdrant generation filtering
  controls visibility;
- the original is stored and checksum-verified before the version/job transaction
  is accepted; orphan cleanup handles a later database failure;
- object storage must eventually support streamed I/O, metadata lookup, checksum
  verification, and conditional create-if-absent semantics; and
- owners/admins may request a forced rebuild, while a member may retry a failed job
  they requested. Every manual action creates or uses the successor-job rules in
  ADR 0007 and remains audited.

### Identity layers

| Layer | Identity and uniqueness |
| --- | --- |
| API request | Workspace, operation, client idempotency key, and canonical request hash |
| Document version | Existing document ID, content SHA-256, and complete pipeline fingerprint |
| Job | Workspace, document version, operation, pipeline fingerprint, and logical request identity |
| Attempt | Job ID plus monotonically increasing attempt number and fenced attempt UUID |
| Output generation | One immutable generation UUID per attempt that reaches output writing |
| Chunk | Pipeline fingerprint, canonical source locator, and normalized chunk-content hash |
| Vector point | Deterministic UUID derived from workspace, document version, generation, chunk identity, and vector kind |
| Dispatch/audit event | Stable event UUID protected by a unique consumer/application key |

All uniqueness that carries tenant meaning includes or is constrained through the
trusted workspace relationship. Filenames, queue message IDs, worker IDs, and
provider-generated object versions are metadata, not logical identity.

### Request replay contract

The API stores an idempotency record and canonical request hash with the job-creation
transaction. Reusing the same key and equivalent request returns the existing
document version/job and original response semantics. Reusing the key with a
different request returns a safe conflict. Concurrent inserts converge through a
database uniqueness constraint rather than an application-only pre-check.

The client must supply the stable key. The authenticated frontend generates and
retains one before submission. Missing keys are rejected; automatic network retries
repeat the same key and canonical request.

### Complete pipeline fingerprint

The pipeline fingerprint is the hash of a canonical, versioned manifest containing
at least:

- parser/OCR implementations, versions, normalization rules, and relevant options;
- chunking algorithm, boundaries, overlap, and locator-schema revision;
- enrichment and prompt revisions that change persisted artifacts;
- embedding provider/model revision, dimensions, normalization, and vector kind;
- Qdrant payload/vector schema revision; and
- citation/source-locator schema revision.

Secrets, credentials, environment-specific endpoints, and runtime worker identity
are excluded. Canonical serialization and test fixtures must make the same manifest
hash identically across API and worker processes. A material fingerprint change
creates a new document version, preserving ADR 0004 identity.

### Immutable outputs

The original object is content-addressed or conditionally created, with size,
media type, and SHA-256 verified before a job is accepted. Derived objects use an
attempt/generation namespace such as:

```text
workspaces/{workspace_id}/documents/{document_id}/versions/{version_id}/
  attempts/{attempt_id}/artifacts/{artifact_kind}/{content_sha256}
```

Exact bucket names and the S3-compatible provider remain undecided. The storage
adapter must eventually support streamed reads/writes, checksum verification,
metadata lookup, and conditional create; ADR selection of an implementation is
deferred.

Vectors are written with trusted workspace, document, version, generation, chunk,
and vector-kind payload fields. Point IDs are deterministic within a generation,
so replaying an attempt converges. A retry with a new attempt writes a new generation
rather than mutating or deleting the active one.

### Validation and promotion

1. The fenced attempt writes all derived objects and vectors into its generation.
2. It records an immutable manifest with expected artifact checksums, chunk/vector
   counts, pipeline fingerprint, and scope.
3. It validates that the generation is complete and tenant-scoped.
4. One PostgreSQL transaction verifies the current attempt/fencing token, records
   the manifest, changes the document version's active generation pointer, marks
   the job/attempt succeeded, and appends the safe audit event.
5. Retrieval resolves the active generation from authorized PostgreSQL state and
   includes that generation in mandatory Qdrant filters.

Before step 4, the new generation is invisible. After step 4, it is authoritative;
a worker replay observes terminal success and does no further promotion. On a first
index there is no active generation until promotion. During reprocessing, the
previous active generation remains queryable until the replacement commits.

This avoids pretending PostgreSQL, object storage, and Qdrant share a transaction.
External outputs are prepared first and made visible through one relational pointer.
Failure before promotion leaves an unreferenced generation, not a partially active
index. Failure after promotion is recovered from the committed terminal state.

### Duplicate and recovery behavior

| Condition | Required outcome |
| --- | --- |
| Same request key and hash | Return the existing logical response/job |
| Same request key, different hash | Safe conflict; do not mutate prior work |
| Duplicate queue delivery with active lease | No second attempt starts |
| Duplicate delivery after terminal success | No-op after durable-state reload |
| Retry after partial writes | New generation; prior partial generation stays invisible |
| Crash immediately before promotion | Active generation unchanged; retry/recovery is safe |
| Crash immediately after promotion | Terminal database state wins; no duplicate promotion |
| Reindex while a ready generation exists | Continue serving the ready generation until replacement promotion |

### Retention and garbage collection

Garbage collection may delete only generations that are not referenced as active,
are not owned by a live attempt, and are older than an approved retention window.
The collector rechecks those conditions under durable state immediately before
deletion, records safe counts/results, and treats missing objects or points as an
idempotent success. Request and worker paths never perform delete-before-replace.

## Consequences

- API retries, duplicate delivery, and worker recovery converge without duplicate
  visible outputs.
- Retrieval always sees either the previous validated generation or the newly
  promoted one, never a mixture.
- Reprocessing requires generation-aware PostgreSQL and Qdrant queries.
- Failed attempts may temporarily consume object/vector capacity until controlled
  garbage collection runs.
- The pipeline manifest becomes a compatibility contract requiring explicit
  revision whenever output-affecting behavior changes.

## Deferred details

- Idempotency-record and inactive-generation retention windows must be accepted
  before garbage collection is enabled. Until then, the safe behavior is retention.
- The canonical multimodal source-locator fields must be finalized before Phase 3
  changes chunk/vector identity; the contract requires a versioned locator plus
  normalized content hash rather than ordinal position alone.
- ADR 0011 must map checksum and conditional-create capabilities to the selected
  S3-compatible provider without weakening this contract.

## Acceptance evidence required

- Concurrent request tests prove same-key replay and different-hash conflict behavior.
- Canonical pipeline-manifest fixtures hash identically across processes.
- Duplicate-delivery and lease-expiry tests create no duplicate visible generation.
- Fault injection before and after every promotion step preserves the prior active result.
- Retrieval tests require workspace, document version, and active generation filters.
- Garbage-collection tests cannot delete active or live-attempt outputs.
- No object key, manifest, error, or audit record contains a secret or untrusted path.

## Implementation evidence on 2026-08-30

- Alembic revision `20260830_0008` adds attempt-owned immutable generations and a
  tenant-constrained active-generation pointer on each document version.
- The canonical pipeline manifest and fingerprint cover parser, chunking, model,
  vector, citation, and schema versions. Attempt and final manifest objects use
  trusted opaque keys and verified SHA-256/byte identities.
- Async vector point IDs and payloads include the generation. Retrieval resolves the
  authorized active pointer from PostgreSQL and requires it in the Qdrant filter.
- One fenced transaction validates ownership and manifest counts, promotes the
  generation, updates document readiness, and completes the attempt/job. Duplicate
  terminal delivery is a no-op; cancellation before promotion abandons the generation.
- Tests prove idempotent API replay/conflict, duplicate delivery, retry isolation,
  cancellation precedence, one visible promoted generation, and mandatory generation
  scope. Inactive-generation deletion remains disabled pending the separately required
  retention-window decision recorded above.
