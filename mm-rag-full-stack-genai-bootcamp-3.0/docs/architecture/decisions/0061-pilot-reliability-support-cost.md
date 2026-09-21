# ADR 0061: Pilot reliability, support, capacity, and cost

- Status: Proposed
- Date: 2026-09-20
- Milestone: 11.4

## Context

The single-host OCI deployment passed ten-user capacity and recovery gates, but an
invitation-only pilot introduces real support expectations. It remains a learning system,
not a highly available production service.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Promise production availability | Clear expectation | Unsupported by the single-host free topology |
| Upgrade infrastructure before evidence | More headroom | Cost and complexity without measured need |
| Publish learning-pilot expectations and stop conditions | Honest and free-first | Planned downtime and manual support remain |

## Recommendation

Keep the current free-first host, approved pilot SLOs, backup/recovery controls, and
manual support. Publish a learning-pilot availability statement with planned maintenance,
no emergency guarantee, and immediate pause when safety, authorization, integrity,
capacity, or cost gates fail.

## Questions for approval

- What support hours and response target should participants expect?
- Should the pilot pause after any critical alert or only after repeated failure?
- What measured threshold would trigger a paid-capacity decision review?
