# ADR 0040: Dedicated frontend and edge boundary

- Status: Accepted
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

Deploy the existing Streamlit application first. Then build a bounded
Next.js/TypeScript vertical-slice candidate with Auth0 authorization-code flow, secure
server-managed session cookies, CSRF protection, and FastAPI as the final authorization
boundary. The first slice covers sign-in, workspace overview, library, job progress,
chat, and evidence. Preserve Streamlit as the working interface, rollback, and
operator/demo surface until the candidate passes feature-parity and accessibility gates.

Terminate TLS and apply bounded request-size, timeout, security-header, and rate-limit
controls at the reverse proxy. Use a free stable hostname for the learning deployment;
do not require a purchased domain.

## Recommendation

Approve Next.js as a candidate, not the promoted frontend. Deploy Streamlit first,
measure the bounded vertical slice, and promote only after a separate evidence review.

## Approval questions

1. Approve Next.js/TypeScript as the dedicated frontend candidate?
2. Keep Streamlit as rollback until parity and accessibility evidence passes?
3. Approve server-managed sessions and FastAPI as the authorization authority?

## Consequences

- Frontend and API can version and deploy independently.
- The project temporarily maintains two user interfaces during migration.
- No frontend may derive tenant scope or bypass backend policy.

## Decision record

Accepted by the user on 2026-09-13 after reviewing why Next.js is useful and where
Streamlit remains sufficient. Streamlit deploys first and stays authoritative until a
bounded Next.js candidate passes parity, security, accessibility, and resource checks.
