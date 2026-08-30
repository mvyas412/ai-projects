# Phase 2 demonstration runbook

This runbook produces a repeatable, presentation-ready walkthrough without
changing or depending on the immutable V1 checkout.

## Before the session

1. From `mm-rag-full-stack-genai-bootcamp-2.0`, run `make setup` once.
2. Confirm ignored `.env` and `.streamlit/secrets.toml` contain the local Auth0,
   PostgreSQL, Qdrant, and OpenAI settings. Never screen-share those files.
3. Run `make services`, then `make migrate`.
4. In separate terminals run `make api` and `make ui`.
5. Run `make check-acceptance`; all deterministic release checks and the isolated
   real-OpenAI multimodal acceptance must pass before presenting. This command
   makes paid OpenAI requests and removes its temporary SQL, file, and Qdrant data.
6. Open `http://127.0.0.1:8502`, sign in, and confirm the expected workspace.

## Five-minute product story

1. **Overview:** establish the workspace, indexed-readiness, collections, and
   persistent-conversation metrics. In a new workspace, **Add your first document**
   opens Library with the upload form expanded.
2. **Library:** upload a representative PDF or DOCX, explain immutable versions,
   click **Index**, and wait for the READY badge. Show authorized source download.
3. **Collections:** create a focused collection and add the indexed document.
4. **Ask:** explain workspace, collection, and selected-document scope, then start
   a collection-scoped conversation. Ask one factual question and
   one comparison question. Open **Inspect evidence** to show source, page, excerpt,
   retrieval score, and original download.
5. **Persistence:** refresh the page or sign out/in and reopen the conversation.
6. **Activity:** show the signed-in user's Auth0 display name and the human-readable
   upload, index, organization, and answer history—without secrets, raw internal
   identifiers, or model prompts being treated as audit details.
7. **Settings:** finish with Auth0 display name/email, workspace role, PostgreSQL/Qdrant
   readiness, and the backend-enforced authorization explanation.

## Suggested prompts

- “Summarize the three most important findings and cite each one.”
- “Compare the key figures across the available sources.”
- “Which parts of this question cannot be answered from the indexed evidence?”

## Failure-safe talking points

- An unauthorized workspace/resource is hidden with HTTP 404.
- Missing indexed evidence returns a clear conflict instead of hallucinating.
- Model/vector dependency failures return a safe 503 and do not persist a partial chat.
- Every retrieval is constrained by tenant, workspace, document, and version IDs.
- V1 remains recoverable from `mm-rag-v1.0.0`; Phase 2 is isolated on its own branch.

## Visual acceptance checklist

- Review Overview, Library, Ask, Activity, and Settings at desktop width.
- Narrow the browser and verify cards, forms, navigation, and chat remain usable.
- Check light and dark themes for readable text, badges, buttons, and focus states.
- Exercise empty, loading, success, validation, 409, and 503 states.
- Confirm evidence excerpts wrap cleanly and original downloads work.
- Confirm the sidebar and Settings show the expected Auth0 display name/email.
- Confirm Ask explains all three scopes and Activity contains no `None` or raw UUID details.
- Confirm no token, key, database URL, internal exception, or private context appears.

## Acceptance record

Phase 2 visual acceptance completed on 2026-08-30. Authenticated screenshots verify:

- The Overview remains coherent at the supplied narrow viewport and presents its
  metrics, current work, readiness, and evidence lifecycle clearly.
- Light and dark themes retain readable contrast, hierarchy, borders, links, and badges.
- The sidebar and Settings consistently present the Auth0 identity and workspace role.
- Activity presents the current actor and readable action details without null values,
  raw UUIDs, secrets, or internal implementation fields.
- The empty-workspace first-document CTA remains covered by automated regression tests;
  it is intentionally absent from the reviewed workspace because a document exists.
