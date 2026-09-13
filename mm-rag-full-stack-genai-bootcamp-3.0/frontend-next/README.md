# Next.js parity candidate

This is the bounded, evaluation-only candidate accepted by ADR 0040. Streamlit remains
the authoritative Phase 8 frontend. The candidate covers authenticated workspace
overview, library, ingestion-job progress, conversation, and evidence views.

The browser calls only the same-origin BFF route. The BFF allowlists backend paths,
checks the origin of mutations, and obtains Auth0 access tokens server-side. The SDK's
browser access-token endpoint is disabled. Never add `NEXT_PUBLIC_` token or API-secret
variables.

Local checks:

```bash
npm ci
npm test
npm run typecheck
npm run build
```

Required runtime settings are `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, `AUTH0_CLIENT_SECRET`,
`AUTH0_SECRET`, `AUTH0_AUDIENCE`, `APP_BASE_URL`, and `MM_RAG_INTERNAL_API_URL`.
The Auth0 application needs candidate callback/logout/web-origin URLs before a browser
acceptance. Promotion requires measured security, accessibility, resource, and parity
evidence; this directory alone does not promote the candidate.
