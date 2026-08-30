# ADR 0005: Backend-mediated RAG and scoped persistent conversations

- Status: Accepted
- Date: 2026-08-30
- Milestone: 2.3

## Context

The preserved prototype lets Streamlit orchestrate retrieval and generation.
Phase 2 requires durable chat and a security boundary that prevents browsers from
choosing vector filters or persisting citations outside their authorized scope.

## Decision

1. FastAPI is the only Phase 2 product boundary allowed to construct retrieval
   requests, call model services, and persist assistant output.
2. Conversations target an entire workspace, one collection, or an immutable set
   of explicit document identities. PostgreSQL composite keys enforce workspace
   consistency for explicit targets and messages.
3. Each request resolves only the latest READY version of every active authorized
   document. Client input never supplies vector payload filters or version IDs.
4. The Qdrant filter always combines tenant/workspace predicates with the resolved
   document/version pairs. Every returned citation is revalidated against that
   authorized set before messages are committed.
5. User and assistant messages are committed atomically only after successful
   retrieval and generation. Citations, sequence, model identity, and token counts
   are durable product metadata.
6. Indexing and answer generation use replaceable protocols. Phase 2 provides a
   synchronous OpenAI/Qdrant implementation; Phase 3 will move indexing to durable
   jobs without changing the API's document/version identity.
7. Missing or failed model dependencies return non-disclosing 503 responses.
   Empty indexed scope returns 409. Unauthorized resources remain non-enumerating 404s.

## Consequences

- Chat can resume after logout or process restart.
- Authorization is enforced before retrieval and again before persistence.
- The UI can render inspectable, structured evidence without trusting model text.
- Synchronous indexing can be slow and is intentionally superseded by Phase 3 jobs.
- Live model acceptance needs a locally configured OpenAI key; deterministic fakes
  cover the complete security and persistence flow in automated tests.
