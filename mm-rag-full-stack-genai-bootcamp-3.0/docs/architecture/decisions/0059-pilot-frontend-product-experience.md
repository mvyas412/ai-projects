# ADR 0059: Pilot frontend and product experience

- Status: Accepted
- Date: 2026-09-20
- Milestone: 11.2

## Context

Streamlit is accepted and deployed. A Next.js candidate exists but remains unpublished
and unpromoted. A pilot should optimize user learning without changing the frontend and
authentication boundary unnecessarily.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Keep Streamlit and refine flows | Lowest change risk | Less control over advanced UX |
| Promote Next.js before pilot | More product-like frontend | Requires full parity, security, and operations proof |
| Run both frontends | Direct comparison | Doubles support and creates inconsistent behavior |

## Recommendation

Keep Streamlit authoritative for the initial pilot. Improve only measured onboarding,
library, progress, chat, evidence, settings, accessibility, and recovery pain points.
Leave Next.js deferred until pilot evidence justifies a separate parity decision.

## Accepted decision

Streamlit remains authoritative. Internal rehearsal covers authentication, personal
workspace defaulting, upload and asynchronous controls, library readiness, grounded
chat and citations, feedback, access revocation, support/pause, and recovery. Next.js
promotion requires a separate parity decision supported by repeated measured pain or
an accessibility/security issue that cannot reasonably be corrected in Streamlit.
