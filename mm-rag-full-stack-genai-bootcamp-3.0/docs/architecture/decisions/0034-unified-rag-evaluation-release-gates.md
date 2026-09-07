# ADR 0034: Unified RAG evaluation and release gates

- Status: Accepted
- Date: 2026-09-07
- Milestone: 7.2

## Context

Phases 5 and 6 created protected retrieval and visual/table evaluations, but parsing,
retrieval, answer, citation, latency, safety, and cost evidence are still split across
specialized runners. Phase 7 needs one provider-neutral contract for candidate
comparison without weakening frozen historical gates or exposing protected data.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Adopt a hosted evaluation platform | Rich UI and rapid setup | Cost, private-data transfer, lock-in, and duplicate release authority |
| Replace existing fixtures with one new benchmark | Uniformity | Invalidates accepted evidence and loses specialized protections |
| Compose existing versioned suites under one manifest and result schema | Preserves evidence and adds one gate | Requires adapters and careful split/provenance handling |

## Proposed decision

Build a repository-owned evaluation orchestrator that composes, rather than rewrites,
the existing Phase 5 and Phase 6 contracts. A versioned manifest fingerprints the
dataset, split, parser, chunker, embedding, retrieval, prompt, model, calculation,
and evidence policies. Results use one content-safe schema for quality, identity,
latency, safety, provider calls, and estimated cost.

Required CI stays deterministic and free. Protected validation and holdout ordering
remains enforced. Paid/provider runs require fresh bounded approval. Deterministic
identity, authorization, citation, calculation, and abstention checks are release
authority; an LLM judge may supply supplementary scored evidence but cannot override
those failures. Historical Phase 5/6 results remain immutable.

## Recommendation

Approve the repository-owned composition layer. It reuses trusted evidence, avoids
a new paid dependency, and creates a single pre-promotion report without pretending
that one aggregate score explains RAG quality.

## Approval questions

1. Approve composing the existing Phase 5/6 suites instead of replacing them?
2. Keep deterministic free CI as required and paid judging explicitly opt-in?
3. Require candidate fingerprints and validation-before-holdout across all suites?

## Consequences

- Candidate changes get one reproducible, comparable release report.
- New datasets must declare license, provenance, split policy, and privacy class.
- No historical holdout or failed-candidate evidence is silently retuned.

## Decision record

Accepted by the user on 2026-09-07. The repository-owned composition layer is the
Phase 7 release-evaluation authority; paid judging remains separately authorized.
