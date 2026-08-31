# ADR 0010: RabbitMQ ingestion broker

- Status: Accepted
- Date: 2026-08-30
- Milestone: 3.0

## Context

ADR 0009 requires an at-least-once broker boundary between the PostgreSQL outbox
dispatcher and ingestion workers. The broker is a wake-up mechanism only:
PostgreSQL remains authoritative for job state, attempt ownership, authorization,
retry timing, cancellation, and terminal outcomes.

The first Phase 3 environment must run locally without a paid managed service.
The design must still support durable delivery, explicit acknowledgements,
publisher confirmation, backpressure, dead-letter evidence, and independent
dispatcher/worker scaling.

## Decision drivers

- Free, self-hosted local development and CI operation.
- Durable at-least-once delivery with publisher confirms and manual consumer acknowledgements.
- Mature Python client support and straightforward Docker operation.
- Bounded consumer prefetch so one worker cannot reserve an unbounded backlog.
- Dead-letter isolation for malformed or repeatedly rejected messages.
- No broker-specific authorization, document metadata, or job truth.
- A migration path to clustered production operation without changing the domain model.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| RabbitMQ | Mature AMQP broker, durable queues, publisher confirms, manual acknowledgements, backpressure, and free open-source local operation | Adds a service to operate; quorum durability needs a multi-node production cluster |
| Amazon SQS | Fully managed, durable, simple scale, native AWS integration | Usage-priced and cloud-dependent; local testing needs an emulator; couples the first implementation to AWS |
| Redis Streams | Familiar operational footprint and simple consumer groups | Retention, delivery recovery, and dead-letter behavior need more application policy; Redis would gain another critical role |
| Apache Kafka | Strong replay and high throughput | Operationally heavy for a job wake-up queue; partition/retention semantics exceed the current requirement |
| PostgreSQL polling only | No additional service | Creates persistent database polling/locking load and erases the accepted independent broker boundary |

## Decision

Use the open-source RabbitMQ distribution as the Phase 3 ingestion broker. Local
development and CI run a self-hosted RabbitMQ container and incur no managed-service
fee. Production hosting, support, and infrastructure cost remain deployment choices;
this ADR does not claim that operating infrastructure is cost-free.

RabbitMQ receives only the versioned minimal event from ADR 0009. A consumer must
reload the job by `job_id` from PostgreSQL and win the fenced claim from ADR 0007.
Possessing or delivering a RabbitMQ message never authorizes access and never proves
that the job is eligible to run.

### License and cost boundary

RabbitMQ identifies its open-source distribution as free software under the Mozilla
Public License 2.0. Commercial support and managed hosting are optional and are not
selected by this ADR. The implementation must use the open-source image and must not
provision a paid broker service.

References:

- <https://www.rabbitmq.com/>
- <https://www.rabbitmq.com/blog/2024/05/31/new-community-support-policy>

### Queue topology

- Use one durable quorum queue for `ingestion.job.available` events.
- Use durable exchange, queue, and binding declarations that are safe to repeat.
- Use a separate durable dead-letter queue for operational evidence.
- Keep local development single-node; require at least three RabbitMQ nodes before
  claiming production quorum fault tolerance.
- Do not use auto-delete or exclusive queues for ingestion work.
- Do not rely on broker-generated message IDs or deduplication for correctness.

The initial routing names are configuration, not public API. They may change without
changing the event schema or PostgreSQL contract.

### Publisher contract

The dispatcher must:

1. declare the expected durable topology;
2. publish a persistent message containing only the ADR 0009 payload;
3. use the outbox `event_id` as the stable message ID and correlation value;
4. require a positive publisher confirm before recording `published_at`;
5. treat rejection, timeout, connection loss, or ambiguous acknowledgement as
   unpublished and retry the same event ID through ADR 0009; and
6. never log credentials, raw message bodies, filenames, object keys, or content.

### Consumer contract

Workers use manual acknowledgements and an initial prefetch count of `1` per worker
process. A worker acknowledges only after the corresponding durable PostgreSQL
transition is committed. Connection loss before acknowledgement may redeliver the
message and must remain harmless.

The consumer behavior is:

- terminal, cancelled, superseded, or no-longer-eligible job: record only the safe
  required operational result, then acknowledge as a no-op;
- fenced claim lost to another attempt: acknowledge as a duplicate no-op;
- retryable worker failure after a durable `retry_scheduled` transition and outbox
  insertion: acknowledge the current message;
- terminal worker failure after the durable terminal transition: acknowledge;
- transient failure before a durable transition: reject for redelivery without
  acknowledging success;
- malformed or unsupported event contract: reject without requeue to the dead-letter
  queue and emit a non-disclosing operational alert.

Broker redelivery counts and dead-letter records are not job execution attempts.
Only PostgreSQL attempt rows count toward the ADR 0007 limit.

### Security and operations

- Credentials come from ignored environment or secret-management configuration.
- Use a least-privilege RabbitMQ virtual host and application user.
- Do not expose the management interface outside the local machine in the default DEV stack.
- Health checks must distinguish TCP/process availability from usable authenticated topology.
- Metrics must include connection status, publish confirms/failures, ready and unacknowledged
  message counts, consumer count, redeliveries, and dead-letter depth.
- Queue depth is operational telemetry, not a substitute for PostgreSQL job counts.

## Consequences

- The free local Phase 3 stack gains one additional stateful service.
- RabbitMQ outages delay dispatch but cannot lose a committed job or outbox event.
- At-least-once delivery makes duplicate messages normal and safe.
- Production quorum durability requires a deliberately operated multi-node deployment.
- A future broker change can preserve the same outbox payload and worker claim contract.

## Accepted initial defaults

| Topic | Initial value |
| --- | --- |
| Distribution | Open-source RabbitMQ |
| Local/CI deployment | Self-hosted container; no paid service |
| Queue type | Durable quorum queue |
| Delivery | At least once |
| Publisher acknowledgement | Required publisher confirm |
| Consumer acknowledgement | Manual, after durable PostgreSQL transition |
| Prefetch | 1 per worker process |
| Dead letters | Separate durable operational queue |
| Message authority | Wake-up hint only; PostgreSQL reload required |

## Acceptance evidence required

- Local RabbitMQ starts without a paid account or external service.
- Topology declarations are idempotent and the queue is durable.
- Publisher-confirm success is required before an outbox row is marked published.
- Ambiguous publish acknowledgement republishes the same event ID safely.
- Duplicate and redelivered messages cannot create overlapping valid attempts.
- Prefetch remains bounded and worker shutdown does not lose an unacknowledged event.
- Malformed messages reach the dead-letter queue without exposing sensitive payloads.
- Broker outage/recovery does not consume job attempts or strand committed outbox rows.

## Implementation evidence on 2026-08-30

- The local/CI stack runs free self-hosted RabbitMQ `4.2.3` with a localhost-only
  management port and isolated virtual host. The runtime declares durable direct
  exchanges, a quorum main queue, a quorum dead-letter queue, and a delivery limit.
- The dispatcher publishes persistent minimal messages with mandatory routing,
  stable message/correlation IDs, and publisher confirms. The consumer uses prefetch
  `1`, strict parsing, manual acknowledgements, safe requeue, and malformed-message DLQ.
- A real local integration test creates uniquely named temporary topology, confirms
  publication, validates and manually acknowledges the delivery, then removes only
  those temporary queues/exchanges. Unit tests cover unconfirmed retry and job state.
