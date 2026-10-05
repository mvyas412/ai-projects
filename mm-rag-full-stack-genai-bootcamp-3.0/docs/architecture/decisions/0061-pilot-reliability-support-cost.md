# ADR 0061: Pilot reliability, support, capacity, and cost

- Status: Accepted
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

## Accepted decision

Keep the existing free-first topology and no production SLA. Authorization, privacy,
integrity, secret, cross-tenant, unexpected-cost, and recovery failures pause the pilot
immediately. Ordinary performance issues are remediated within the active stage. Any
paid-capacity review requires a separate decision supported by measured evidence. The
support target is best effort within one business day.
