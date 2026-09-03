# ADR 0030: Region evidence, viewer, and Phase 6 rollout

- Status: Accepted
- Date: 2026-09-02
- Accepted: 2026-09-03
- Milestone: 6.5

## Context

The current answer contract exposes document title, content type, page number, and
text excerpt. It cannot point to a figure/table bounding box, identify exact table
cells, show calculation operands, or render an authorized crop. Phase 6 also needs
a rollout boundary that does not replace the accepted text path before measured
visual/table evidence passes.

## Decision drivers

- Let users inspect the exact authorized region used for an answer.
- Preserve backend authorization and avoid exposing object-store coordinates.
- Validate citations against retrieved identities rather than model-generated labels.
- Make exact calculations explainable without exposing internal SQL or hidden prompts.
- Keep the current text evidence UI and retrieval profile as a rollback.
- Separate free deterministic acceptance, optional paid evidence, browser proof,
  promotion, and release tagging.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Keep page-number citations only | No API/UI change | Users cannot verify which figure, table, or cells support a claim |
| Return object-store URLs and draw client-side overlays | Reduces API streaming work | Exposes provider coordinates and complicates revocation and integrity checks |
| Let the answer model emit coordinates/cell ranges | Flexible | Coordinates are hallucination-prone and bypass retrieved-identity validation |
| Backend-resolved evidence descriptors plus authorized artifact streaming | Exact scope, integrity, and auditability | Requires versioned API schemas and viewer work |

## Decision

### Evidence contract

Extend citations with a versioned evidence descriptor containing:

- evidence kind (`text`, `figure`, `chart`, `diagram`, `image`, `table`, or
  `calculation`);
- document, version, active generation, page, region, and artifact identities;
- normalized bounding box and page geometry for region evidence;
- table and ordered cell identities for tabular evidence; and
- calculation-trace identity for exact results.

The answer model receives opaque evidence labels and cannot invent trusted IDs or
coordinates. The backend accepts only citations that map to the authorized retrieved
set and current active generation. Invalid citations are dropped or cause safe
abstention under a versioned policy.

Add backend endpoints that resolve an evidence descriptor, recheck current policy,
verify artifact checksum/media type/size, and stream the page render or crop. The
browser never submits or receives a trusted bucket/key pair and receives no provider
credentials or internal error detail.

### Viewer behavior

The Streamlit evidence viewer should:

- open the cited page with the region highlighted;
- offer the exact crop and OCR/source caption/generated-description layers with
  clear provenance labels;
- render a structured table and highlight the cited cells;
- show calculation operator, human-readable operands, units, rounding, and result;
- distinguish extracted source data from generated summaries; and
- preserve loading, empty, inaccessible, stale-generation, tombstoned, and integrity-
  failure states without disclosing whether an unauthorized resource exists.

Accessibility requires keyboard operation, meaningful text alternatives, zoom,
non-color-only highlighting, and readable light/dark contrast.

### Rollout and acceptance

Introduce a versioned Phase 6 profile that can be enabled per environment and
evaluated without changing `hybrid-v1`, `dense-v1`, or frozen `hybrid-v3`. The
rollout order is:

1. deterministic fixture and security tests;
2. free live-service and local-model tests;
3. frozen candidate validation and, only after it passes, holdout;
4. separately authorized paid/provider comparison if still needed;
5. signed-in browser proof of visual/table retrieval, exact calculation, evidence
   inspection, persistence, tenant denial, and safe fallback;
6. explicit user acceptance and profile promotion; and
7. a separate explicit decision before creating an `mm-rag-v6.0.0` tag.

Failure at any gate preserves the current product default and records an honest
non-acceptance outcome. No successful model metric alone authorizes promotion.

## Recommendation

Approve backend-resolved evidence descriptors and authorized artifact streaming,
with a viewer that clearly separates source extraction, generated enrichment, and
exact calculation. Keep rollout and release tagging as explicit gates so Phase 6
cannot silently replace the accepted text path.

## Consequences

- Users can verify visual and numerical evidence at the exact source location.
- Citation schemas and frontend states become richer and require compatibility tests.
- Backend streaming consumes bandwidth but preserves the accepted authorization model.
- A Phase 6 candidate can remain opt-in if quality, latency, cost, accessibility,
  or browser evidence does not pass.

## Acceptance resolution

The user approved all recommendations on 2026-09-03: the evidence descriptor;
backend-mediated, integrity-checked page/crop streaming; the viewer provenance and
accessibility behavior; and the seven-step rollout with separate promotion and
release-tag decisions.

## Acceptance evidence required after approval

- API schema compatibility and citation-negative tests pass.
- Unauthorized, stale, tombstoned, cross-generation, and checksum-failed evidence
  returns non-disclosing errors and no bytes.
- Desktop/narrow and light/dark browser checks cover region, table, calculation,
  loading, failure, and keyboard states.
- Refresh and sign-out/sign-in preserve authorized evidence while revocation blocks it.
- No token, secret, raw object key, private source content, or internal provider error
  appears in logs, URLs, audit events, or public UI state.
