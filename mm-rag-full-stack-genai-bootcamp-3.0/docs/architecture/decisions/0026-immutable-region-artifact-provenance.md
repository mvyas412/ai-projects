# ADR 0026: Immutable region and derived-artifact provenance

- Status: Proposed
- Date: 2026-09-02
- Milestone: 6.1

## Context

Current vector payloads identify a document version, generation, page, and text
chunk, but they do not identify a figure/table region or a derived crop. Phase 6
will create page renders, crops, OCR, captions, visual vectors, structured tables,
and calculation evidence across PostgreSQL, Qdrant, and object storage. A provider
coordinate, filename, page number, or model-generated caption is not sufficient
provenance.

ADRs 0008, 0015, and 0017 require immutable attempt-scoped outputs, PostgreSQL-
controlled promotion, trusted cross-store scope, and governed deletion. Phase 6
artifacts must extend those contracts without introducing an independent visibility
boundary.

## Decision drivers

- Trace every answer to an immutable document version, generation, page, and region.
- Keep PostgreSQL authoritative for visibility and lifecycle.
- Store binary crops/renders in object storage and search representations in Qdrant.
- Make extractor/model revisions and output checksums reproducible.
- Preserve tenant RLS, mandatory vector filters, backend-mediated object access,
  active-generation promotion, and tombstone-first deletion.
- Support future corrected extraction without mutating accepted history.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Store region metadata only in Qdrant payloads | Simple retrieval path | Weak relational integrity, difficult lifecycle reconciliation, and payloads become an authority they should not have |
| Store one JSON manifest only in object storage | Immutable and portable | Expensive lookup, weak RLS, and no transactional promotion/reference checks |
| Store every crop and OCR blob directly in PostgreSQL | One transactional store | Bloats the database and duplicates object-storage responsibilities |
| PostgreSQL provenance index plus immutable object artifacts and denormalized Qdrant identity | Fits existing trust boundaries and supports reconciliation | Requires schema, cross-store validation, and promotion checks |

## Proposed decision

Create immutable, generation-scoped `content_regions` and `content_artifacts` in
PostgreSQL under the existing tenant RLS and composite foreign-key pattern.

### Region identity

A region belongs to exactly one workspace, document, document version, ingestion
generation, and page. Its stable identity within that generation is derived from a
canonical locator containing:

- page number and page-render checksum;
- region kind (`figure`, `chart`, `diagram`, `photo`, `table`, or `other`);
- top-left-origin normalized bounding box, page width/height, rotation, and locator
  schema revision; and
- detector/extractor revision and deterministic region ordinal.

Coordinates are trusted extractor output, not client input. A materially different
extraction profile creates a successor document version/generation through the
existing fingerprint and promotion contract. Corrections never mutate a promoted
region in place.

### Artifact identity and lineage

An artifact belongs to one region and records artifact kind, immutable object key,
media type, dimensions, byte size, SHA-256, parent-artifact identity, extraction or
model provider/name/revision, prompt/schema revision where applicable, confidence,
validation state, and creation attempt. Artifact kinds initially include page
render, region crop, OCR text, deterministic caption, generated description,
structured table, and normalized tabular export.

Binary artifacts use the ADR 0008 generation/attempt object namespace and
conditional create-if-absent writes. Text used for retrieval may be denormalized to
Qdrant, but PostgreSQL identities and the immutable manifest remain authoritative.
No public API returns raw provider object keys.

### Promotion and lifecycle

Before promotion, the worker verifies every region/artifact scope, checksum,
parent reference, count, and manifest fingerprint. PostgreSQL promotes the complete
generation atomically through the existing fenced transaction. Retrieval includes
the active generation and region identity in mandatory filters and revalidates all
returned payloads.

Inactive visual/table artifacts follow ADR 0017. Automatic deletion remains
disabled unless the existing preview/apply and retention policy explicitly includes
the new data classes.

## Recommendation

Approve PostgreSQL as the provenance authority, object storage for immutable binary
artifacts, and Qdrant only for scoped search representations. Use normalized
top-left coordinates plus original page dimensions so the evidence viewer can
render consistently across devices without losing source precision.

## Consequences

- A visual citation can identify the exact source region and extraction revision.
- PostgreSQL gains several tenant-scoped tables and promotion validations.
- Derived objects consume storage until governed retention makes them eligible.
- Reprocessing duplicates immutable artifacts by generation, trading storage for
  deterministic rollback and auditability.

## Approval questions

1. Approve PostgreSQL as the region/artifact provenance authority?
2. Approve generation-scoped immutable identities and successor-only corrections?
3. Approve normalized top-left bounding boxes plus original page geometry?
4. Approve object-storage binaries, Qdrant denormalization, and existing lifecycle controls?

## Acceptance evidence required after approval

- Migration upgrade/downgrade, RLS, composite-scope, and schema-drift tests pass.
- Deterministic locator and manifest fixtures hash identically across processes.
- Cross-workspace region, artifact, object, vector, and citation attempts fail closed.
- Fault injection before/after promotion exposes no partial visual/table generation.
- Lifecycle preview/apply cannot delete active, held, or live-attempt artifacts.
