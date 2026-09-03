# ADR 0027: Local-first visual extraction and enrichment

- Status: Proposed
- Date: 2026-09-02
- Milestone: 6.1

## Context

The current PDF path uses `pypdf` text extraction and does not emit page images,
figure/table regions, or region coordinates. Standalone image ingestion sends one
image to the configured OpenAI chat model for transcription and description. That
path can demonstrate vision, but it is paid, has no region-level PDF provenance,
and does not provide a deterministic free baseline.

[Docling](https://docling-project.github.io/docling/concepts/docling_document/)
represents text, tables, and pictures as structured document items. Its documented
pipeline supports generated picture images, OCR, and table reconstruction, with
CPU-capable layout and TableFormer modes. It can reuse Tesseract, which is already
a project prerequisite. Docling also supports local and API-backed picture
description options, but generated descriptions can be wrong and therefore cannot
become evidence without evaluation and provenance.

## Decision drivers

- Extract page regions and geometry locally without requiring a paid request.
- Reuse the durable worker, immutable generation, and object-storage pipeline.
- Keep model/provider choices behind narrow adapters and fingerprints.
- Treat OCR, embedded captions, and model descriptions as claims with provenance,
  not source truth.
- Support CPU-only local/CI checks while allowing separately approved quality comparisons.
- Avoid downloading models during request or worker execution.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Extend `pypdf` with hand-built PDF/image heuristics | Small immediate dependency change | Layout, reading order, tables, and scanned pages require substantial custom logic |
| Adopt Docling for local document structure and retain Tesseract | Unified regions, geometry, table structure, and picture exports; local and open source | Adds PyTorch/model artifacts, memory, startup, and integration complexity |
| Send every page/region to a managed vision API | Strong capability and low local model operations | Paid, network-dependent, privacy-sensitive, and expensive at ingestion scale |
| Use a local VLM as the sole parser | One model-shaped path | Hardware-heavy, nondeterministic, weaker structural guarantees, and difficult exact validation |
| Local structural extraction plus optional versioned visual enrichment | Deterministic provenance and free baseline with measured model upgrades | More pipeline stages and artifacts to govern |

## Proposed decision

Introduce provider-neutral `DocumentStructureExtractor`, `RegionRenderer`, and
`VisualEnricher` interfaces inside the existing worker process.

### Local structural baseline

Use Docling as the proposed PDF structure candidate behind the extractor interface,
with Tesseract as the initial OCR engine and Docling's accurate TableFormer mode as
the proposed table-structure candidate. Generate page renders and figure/table crops
locally. Persist only outputs that satisfy ADR 0026 identity, geometry, checksum,
and manifest validation.

The implementation must pin package/model revisions and artifact checksums during
setup or image build. The runtime starts offline and fails the visual/table stage
safely if a required artifact is missing; it never downloads a model in a request
or job path. CPU-only operation remains the required local baseline. GPU/MPS is an
optional measured optimization, not a correctness dependency. Docling documents
CPU installation and multiple OCR engines in its
[installation guide](https://docling-project.github.io/docling/getting_started/installation/).

### Enrichment levels

Use three explicit, separately fingerprinted levels:

1. `structural-v1`: region kind, page context, embedded caption, and OCR only;
2. `local-vision-candidate-v1`: the structural baseline plus a pinned local compact
   VLM description evaluated against ADR 0025; and
3. `managed-vision-candidate-v1`: an optional provider-backed description used only
   in an explicitly authorized benchmark or rollout.

The initial local VLM candidate should be the small model supported by Docling's
[picture-description example](https://docling-project.github.io/docling/_generated/examples/pictures_description/),
subject to exact model-license, checksum, memory, and quality review before lockfile
changes. The existing OpenAI vision capability remains a possible managed comparator;
OpenAI documents image analysis through the Responses or Chat Completions APIs in
its [images and vision guide](https://developers.openai.com/api/docs/guides/images-vision).
It is not a required ingestion dependency and no paid call is authorized by this ADR.

OCR text, source captions, and generated descriptions remain distinguishable fields.
A model description never overwrites source text, table cells, or a human-authored
caption. Low-confidence or invalid output is retained only as non-authoritative
diagnostic evidence or discarded before promotion under a versioned rule.

## Recommendation

Approve Docling plus the existing Tesseract dependency as the local structural
candidate, but require ADR 0025 results before promoting any generated visual
description. Start with the free structural baseline; compare the compact local VLM
and a separately authorized managed vision candidate only if they materially improve
visual retrieval or answer evidence.

## Consequences

- PDF figures and tables gain local region-level structure without mandatory paid calls.
- The worker image and model cache grow, and CPU ingestion will be slower.
- A staged enrichment contract prevents generated prose from being mistaken for
  extracted source content.
- Provider-backed vision remains available for measured quality, not silently embedded
  in every ingestion job.

## Approval questions

1. Approve Docling behind an adapter as the proposed local PDF structure extractor?
2. Approve retaining Tesseract and evaluating accurate TableFormer as the first local path?
3. Approve the three enrichment levels and no generated-description promotion without evidence?
4. Approve paid/provider vision only through a separately authorized candidate run?

## Acceptance evidence required after approval

- Committed fixtures verify reading order, region kinds, geometry, OCR, table regions,
  deterministic hashes, and safe failures without network access.
- Pinned model artifacts and licenses verify during setup, CI, and container build.
- Malformed or low-confidence descriptions cannot overwrite source-derived evidence.
- Worker retry/cancellation and promotion tests leave no partial visible artifact set.
- Latency, peak memory, artifact bytes, and optional provider cost are reported.
