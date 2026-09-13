# ADR 0040: Dedicated frontend and edge boundary

- Status: Proposed
- Date: 2026-09-13
- Milestone: 8.0 and 8.2

## Context

Streamlit proved the product and remains a useful rollback, but Phase 8 calls for a
frontend that can evolve and deploy independently. A browser-only SPA would place more
token handling in the client; a server-capable frontend can keep a tighter session
boundary while FastAPI remains the authorization authority.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Keep Streamlit only | No rewrite and low resource use | Limited independent product/frontend evolution |
| React/Vite SPA | Simple static deployment | More browser token and API security responsibilities |
| Next.js frontend service | Server-side session options, routing, accessibility ecosystem | Adds Node runtime, framework surface, and migration work |

## Proposed decision

Use a dedicated Next.js/TypeScript frontend as the recommended candidate, with Auth0
authorization-code flow, secure server-managed session cookies, CSRF protection, and
FastAPI as the final authorization boundary. Preserve Streamlit as a temporary rollback
and operator/demo surface until feature parity and accessibility checks pass.

Terminate TLS and apply bounded request-size, timeout, security-header, and rate-limit
controls at the reverse proxy. Use a free stable hostname for the learning deployment;
do not require a purchased domain.

## Recommendation

Approve Next.js as the candidate, not yet the promoted frontend. Implement one vertical
slice first—sign-in, workspace overview, library, job progress, chat, and evidence—then
decide whether it is ready to replace Streamlit.

## Approval questions

1. Approve Next.js/TypeScript as the dedicated frontend candidate?
2. Keep Streamlit as rollback until parity and accessibility evidence passes?
3. Approve server-managed sessions and FastAPI as the authorization authority?

## Consequences

- Frontend and API can version and deploy independently.
- The project temporarily maintains two user interfaces during migration.
- No frontend may derive tenant scope or bypass backend policy.

