# ADR 0032: Observability backend and free local stack

- Status: Accepted
- Date: 2026-09-07
- Milestone: 7.0–7.1

## Context

ADR 0031 defines signals but not where they are collected, queried, or visualized.
The development stack needs a reproducible free option, while Phase 8 production
hosting, region, encryption, retention, and budget remain undecided.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Provider-specific SaaS now | Fast setup and managed operations | Cost, external data transfer, lock-in, and premature production choice |
| Jaeger plus Prometheus | Familiar traces and metrics | Separate log/dashboard choices and more integration work |
| OpenTelemetry Collector plus Grafana LGTM stack | Open standards; logs, metrics, traces, and dashboards; free self-hosted development | More local containers and operational surface |
| Collector with file/console export only | Smallest first step | Cannot prove dashboards, queries, retention, or alerts |

## Proposed decision

Use the OpenTelemetry Collector as the only application export boundary. Recommend
the free self-hosted Grafana LGTM development stack—Prometheus-compatible metrics,
Loki logs, Tempo traces, and Grafana dashboards—behind pinned images and isolated
ports. Applications export OTLP to the collector and never depend on a backend SDK.

Local/CI retention must be short, bounded, and disposable. Production hosting,
region, encryption keys, high availability, and paid service selection remain a
Phase 8 decision. Loss of telemetry must not fail product requests or jobs.

## Recommendation

Approve Collector + LGTM for local development because it is free, cohesive, and
replaceable. Keep the production backend explicitly undecided and preserve OTLP as
the portability boundary.

## Approval questions

1. Approve the free local LGTM stack and pinned container images?
2. Approve OTLP/Collector as the sole application export boundary?
3. Keep production observability hosting and retention deferred to Phase 8?

## Consequences

- Compose and live tests gain additional optional services.
- Backend outages degrade observability only; bounded buffering prevents backpressure.
- Cardinality, retention, and resource budgets become explicit acceptance gates.

## Decision record

Accepted by the user on 2026-09-07. The local stack is optional, free, and
replaceable; the Phase 8 production observability provider remains undecided.
