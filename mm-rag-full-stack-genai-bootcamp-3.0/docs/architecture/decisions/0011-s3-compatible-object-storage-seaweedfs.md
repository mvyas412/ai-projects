# ADR 0011: S3-compatible object storage with SeaweedFS for local development

- Status: Accepted
- Date: 2026-08-30
- Milestone: 3.0

## Context

ADR 0008 requires immutable original objects, attempt-scoped temporary outputs,
verified promotion, and database-controlled visibility. Phase 3 therefore needs an
object-storage adapter whose contract is independent of a specific provider.

The first implementation must be free to run locally. Amazon S3 is a useful
production-compatible target but is usage-priced and is not required for local
development. The local provider must exercise the S3 protocol closely enough to
validate the adapter without weakening checksum, immutability, tenant isolation,
or promotion guarantees.

## Decision drivers

- Free, self-hosted local development and CI operation.
- S3-compatible API and support from the standard Python AWS SDK.
- Streamed upload/download without buffering full documents in application memory.
- Immutable keys, conditional creation, metadata inspection, and checksum verification.
- Private-by-default buckets and backend-mediated access.
- Provider-neutral domain interfaces and tests.
- A clear path to Amazon S3 or another compatible production provider later.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| SeaweedFS S3 gateway | Free open-source local operation, active project, S3-compatible API, simple single-node DEV mode | Compatibility must be proven for every required operation; production topology and support require a separate decision |
| Amazon S3 now | Reference S3 behavior, mature durability and operations | Usage-priced, requires cloud credentials/network, and violates the free-local constraint |
| Local filesystem only | Already available and easy to inspect | Does not validate S3 semantics, distributed workers, conditional object creation, or provider portability |
| MinIO Community Edition | Familiar S3-compatible development option | Current distribution/support direction creates avoidable licensing and maintenance uncertainty for this project |
| PostgreSQL large objects | Transactional with relational state | Bloats the primary database and is a poor boundary for streamed binary artifacts |

## Decision

Define an S3-compatible object-storage adapter and use the Apache-2.0 SeaweedFS
open-source distribution for local development and CI. Use the standard Python AWS
SDK at the adapter boundary. No AWS account, S3 bucket, or billable resource is
provisioned by this decision.

Amazon S3 remains a future production option because the application contract is
S3-compatible, but production provider, region, encryption key management, lifecycle,
replication, and cost controls require a later deployment ADR.

### License and cost boundary

The SeaweedFS open-source repository is Apache-2.0 licensed. The implementation
must use that open-source distribution, not an enterprise image or paid managed
service. Local Docker compute, disk, and operator time still have ordinary resource
costs; “free” means no software license fee or cloud service charge is required.

References:

- <https://github.com/seaweedfs/seaweedfs>
- <https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html#Payingforstorage>

### Provider-neutral adapter contract

The application-facing interface must support:

- streamed create from a file-like source;
- streamed read with explicit close semantics;
- metadata/head lookup without downloading the object;
- SHA-256, byte count, media type, and safe provenance metadata;
- conditional create that fails when a key already exists;
- explicit not-found, conflict, unavailable, integrity, and configuration errors;
- bounded multipart upload with abort-on-failure where the provider requires it; and
- optional delete restricted to approved orphan-cleanup or retention workflows.

Provider exceptions, endpoints, credentials, bucket names, and object keys must not
cross the public API boundary. Domain code consumes stable typed outcomes.

### Bucket and key model

Use private buckets separated by lifecycle intent:

- originals: immutable verified source documents;
- artifacts: attempt-scoped temporary files and promoted immutable outputs.

Object keys are generated only by trusted backend code and include opaque stable
workspace/document/version or job/attempt identifiers. User filenames remain safe
metadata and are never used as path segments. Every access begins from an authorized
database row and validates tenant ownership before resolving the object reference.

Keys are write-once. A repeated create at the same key succeeds only as an idempotent
replay after metadata, byte count, and SHA-256 match; otherwise it is an integrity
conflict. Normal application code must not overwrite objects in place.

### Verification and promotion

Every accepted original or generated artifact records and verifies:

- exact byte count;
- application-computed SHA-256;
- expected media type and safe object metadata; and
- the opaque object reference stored in PostgreSQL.

The worker writes outputs to an attempt-scoped temporary key, validates the complete
result, then conditionally creates the immutable final key. PostgreSQL promotion is
fenced and occurs only after the final object is verified. A stale attempt may leave
an unreferenced object for controlled cleanup but can never become the visible version.

Object-store versioning, ETags, or provider checksums may add evidence but do not
replace the application SHA-256 contract. An ETag must not be treated as an MD5 or
content identity.

### Security and access

- Buckets are private; no anonymous listing or read access.
- Credentials remain in ignored environment or secret-management configuration.
- Local credentials are development-only and must not be reused in another environment.
- The backend and worker receive only the minimum bucket operations they need.
- Browser access remains backend-mediated. Presigned URLs are deferred until a
  concrete scale need is accepted; if added, they must be short-lived and tenant authorized.
- Logs and public errors omit object keys, endpoint credentials, raw provider errors,
  document content, and sensitive metadata.

### Compatibility gate

SeaweedFS is accepted only if a live provider contract proves the exact operations
used by the application. Required evidence includes streamed create/read, head,
conditional create conflict, SHA-256/size metadata round-trip, multipart abort,
not-found mapping, restart persistence, and tenant-safe key construction.

If SeaweedFS does not satisfy a required S3 behavior, the project must fix or replace
the provider or adapter through a superseding ADR. It must not emulate away or weaken
the ADR 0008 immutability and promotion invariants.

## Consequences

- Local development and CI can test the distributed object boundary without AWS charges.
- The stack gains one stateful service and persistent local volume.
- S3 compatibility is treated as a tested contract, not an assumption.
- Amazon S3 remains possible later without embedding AWS concepts in domain code.
- Provider-neutral errors and metadata add implementation effort but prevent leakage
  and make migrations safer.

## Accepted initial defaults

| Topic | Initial value |
| --- | --- |
| Local/CI provider | Open-source SeaweedFS S3 gateway |
| Paid cloud resources | None |
| Client boundary | Standard Python AWS SDK behind an application adapter |
| Access | Private, backend mediated |
| Identity | Opaque generated keys plus application SHA-256 and byte count |
| Write behavior | Conditional create; no in-place overwrite |
| Browser presigning | Deferred |
| Production provider | Deferred; Amazon S3 remains an option |
| Deletion | Only explicit orphan cleanup or approved retention workflow |

## Acceptance evidence required

- The local service starts without an external account or paid license.
- Provider contract tests pass against SeaweedFS, not only mocks.
- Streamed paths do not load the entire object into memory.
- Same-key same-content replay is harmless; same-key different-content is rejected.
- Head/read return verified SHA-256 and byte count after service restart.
- Multipart failure aborts temporary provider state where supported.
- Public APIs and logs never disclose credentials, provider endpoints, bucket names,
  raw object keys, or raw provider exceptions.
- An unauthorized workspace cannot resolve or read another tenant's object.
- Existing local-storage behavior remains available only as an explicit development
  fallback until migration and rollback gates are complete.

## Implementation evidence on 2026-08-30

- Boto3 `1.43.83` is locked behind the provider-neutral adapter; domain services do
  not consume SDK types or provider exceptions.
- SeaweedFS `4.43` runs as the open-source local Compose service with isolated data,
  localhost-only S3 exposure, pre-created originals/artifacts buckets, and health checks.
- Unit tests cover streamed identity verification, immutable conditional replay,
  conflict/integrity behavior, safe key construction, configuration, and local fallback.
- The live SeaweedFS contract proves head, streamed put/read, SHA-256/size metadata,
  same-content replay, different-content conflict, delete/not-found behavior, and
  object persistence across a container restart.
- The current maximum upload size is 250 MiB, so the first adapter uses streamed
  single-part PUT. Multipart upload and abort evidence remain mandatory before the
  application limit is raised into provider multipart territory.
- Existing local objects were not migrated or made inaccessible. Enabling the S3
  backend for an existing database requires an explicit migration/rollback step.
