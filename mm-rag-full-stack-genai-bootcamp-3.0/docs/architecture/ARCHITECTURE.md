# Multimodal RAG architecture handbook

> Living architecture baseline — updated 2026-08-31

This document is the version-controlled architecture source of truth for the
complete system and Phases 1–9. Update it whenever a component, boundary, data
flow, technology decision, or phase status changes.

The companion [project plan](../PROJECT_PLAN.md) owns delivery sequence,
milestones, dependencies, completion gates, risks, and immediate next actions.

## Rendered architecture posters

Presentation-ready rendered diagrams are maintained in the
[architecture poster gallery](ARCHITECTURE_POSTERS.md). The gallery includes a
final production-state architecture without phase numbers, a complete-system
roadmap view, and one diagram for each phase. The Mermaid diagrams in this
handbook remain the editable source of truth.

The [current workflow and DEV architecture](current/mm-rag-current-workflow-dev-architecture.svg)
is the accepted Phase 3 checkpoint. It distinguishes the verified asynchronous
product/runtime and signed-in live-model proof from later planned phases.

## Status legend

| Status | Meaning |
| --- | --- |
| Implemented | Present and verified in V1, accepted V2, or accepted Phase 3 |
| In progress | Approved decision or implementation work has started but its phase gate has not passed |
| Planned | Intended capability or boundary that is not implemented yet |
| Proposed / TBD | Candidate design or technology requiring a decision |

The diagrams describe both current and target states. A displayed component is
not necessarily implemented; each phase states its status explicitly.

## Whole-system target architecture

```mermaid
flowchart LR
    user["End user"]
    admin["Workspace / platform admin"]
    sources["PDFs and enterprise sources"]

    subgraph access["Experience and access"]
        web["Web application<br/>Streamlit now; dedicated UI later"]
        edge["Gateway / load balancer<br/>Phase 8"]
        api["Versioned FastAPI API"]
        oidc["Auth0<br/>Managed OIDC identity provider"]
    end

    subgraph product["Identity, policy, and product services"]
        identity["JWT validation and identity mapping"]
        policy["Workspace RBAC / ACL policy"]
        documents["Documents and collections"]
        conversations["Conversations and RAG chat"]
        enterprise["Connectors, usage, quota, billing, audit"]
    end

    subgraph ingestion["Asynchronous ingestion"]
        intake["Upload / connector intake"]
        jobs["Durable job orchestration"]
        outbox["PostgreSQL outbox + confirmed dispatcher<br/>Implemented ADRs 0009/0012"]
        queue["RabbitMQ quorum queue + DLQ<br/>Implemented ADR 0010"]
        workers["Fenced Python ingestion workers<br/>Implemented ADR 0012"]
        parse["PyMuPDF + pdfplumber<br/>Tesseract + Pillow"]
        enrich["Text, table, and visual enrichment"]
        indexer["Embedding and index writer"]
    end

    subgraph rag["Retrieval and generation"]
        query["Authorized query orchestration"]
        dense["Dense / multimodal search"]
        sparse["Sparse / lexical search<br/>TBD"]
        fusion["RRF / score fusion"]
        rerank["Reranking"]
        context["Evidence and citation builder"]
        model["OpenAI / governed model provider"]
    end

    subgraph stores["Persistent data services"]
        pg[("PostgreSQL<br/>identity, metadata, jobs, chat, audit")]
        qdrant[("Qdrant<br/>vectors + tenant-scoped payload")]
        objects[("S3-compatible object storage<br/>SeaweedFS local/CI implemented ADR 0011")]
    end

    subgraph ops["Quality, security, and operations"]
        telemetry["Logs, metrics, traces, cost"]
        evaluation["Datasets, feedback, evaluations"]
        cicd["CI/CD, migrations, security gates"]
        dashboards["SLO dashboards, alerts, runbooks"]
    end

    user -->|"sign in, upload, search, chat"| web
    admin -->|"members, policy, operations"| web
    web <-->|"OIDC authorization-code flow"| oidc
    web -->|"access token + request"| edge
    edge --> api
    api -->|"validate token"| identity
    identity --> oidc
    identity --> policy
    policy <-->|"trusted user/workspace context"| pg
    api --> documents
    api --> conversations
    api --> enterprise
    sources --> enterprise
    enterprise --> intake
    web -->|"upload"| intake
    intake -->|"store immutable original"| objects
    intake -->|"create document version + job"| jobs
    jobs <-->|"state, attempt, idempotency"| pg
    jobs --> outbox
    outbox --> queue
    queue --> workers
    workers --> parse
    parse --> enrich
    enrich -->|"derived visual/table artifacts"| objects
    enrich --> indexer
    indexer -->|"scoped vectors"| qdrant
    indexer -->|"version and index status"| pg
    conversations -->|"authorized scope"| query
    query --> policy
    query --> dense
    query --> sparse
    dense --> qdrant
    dense --> fusion
    sparse --> fusion
    fusion --> rerank
    rerank --> context
    context -->|"permitted grounded evidence"| model
    model -->|"streamed answer"| conversations
    conversations -->|"messages, citations, feedback"| pg
    conversations -->|"answer + source/page evidence"| api
    documents <-->|"metadata and lifecycle"| pg
    documents <-->|"authorized artifact access"| objects
    enterprise --> pg
    api -.-> telemetry
    workers -.-> telemetry
    model -.-> telemetry
    telemetry --> dashboards
    pg --> evaluation
    telemetry --> evaluation
    evaluation -->|"quality and release gates"| cicd
    cicd -->|"deploy and migrate"| api
    cicd -->|"deploy"| workers
```

### End-to-end actions and data flows

1. **Authenticate:** the frontend completes OIDC login and sends an access token;
   FastAPI validates it and resolves trusted user, workspace, and role context.
2. **Ingest:** upload or connector intake stores an immutable original, creates an
   idempotent job, parses and enriches content, and writes versioned metadata to
   PostgreSQL and scoped vectors to Qdrant.
3. **Answer:** FastAPI authorizes scope, runs dense and later sparse retrieval,
   fuses and reranks evidence, sends permitted context to the model, and persists
   the grounded answer and citations.
4. **Govern:** authorization, audit, quota, retention, and observability apply to
   both ingestion and query paths rather than being frontend-only checks.
5. **Improve:** traces, feedback, and curated datasets feed repeatable evaluation
   and CI/CD release gates.

## Phase map

```mermaid
flowchart LR
    p1["Phase 1<br/>Prototype<br/>Implemented"] -->
    p2["Phase 2<br/>Product foundation<br/>Completed"] -->
    p3["Phase 3<br/>Async ingestion<br/>Completed"] -->
    p4["Phase 4<br/>Governance decisions<br/>In progress"] -->
    p5["Phase 5<br/>Hybrid retrieval<br/>Planned"] -->
    p6["Phase 6<br/>Visual/table intelligence<br/>Planned"] -->
    p7["Phase 7<br/>Evaluation/observability<br/>Planned"] -->
    p8["Phase 8<br/>Scalable platform<br/>Planned"] -->
    p9["Phase 9<br/>Enterprise platform<br/>Planned"]
```

| Phase | Capability | Main technologies/components | Stores | Status |
| --- | --- | --- | --- | --- |
| 1 | Working multimodal RAG prototype | Streamlit, LangChain, PyMuPDF, Tesseract, pdfplumber, OpenAI | Qdrant, local files | Implemented and frozen |
| 2 | Backend, identity, workspaces, multi-document product | FastAPI, Pydantic, SQLAlchemy, psycopg, Alembic, Auth0/OIDC, Streamlit | PostgreSQL, Qdrant, temporary files | Completed and accepted; live multimodal model and visual acceptance passed |
| 3 | Durable asynchronous processing | Streamed async API, durable jobs/outbox, RabbitMQ, dispatcher, fenced worker, immutable generations, progress/control UX | PostgreSQL, S3-compatible SeaweedFS, generation-scoped Qdrant | Completed and accepted at `20260830_0008`; signed-in paid promotion/retrieval proof passed |
| 4 | Fine-grained isolation and governance | Proposed central RBAC/ACL, RLS defense, cross-store policy, audit, lifecycle | PostgreSQL, Qdrant, object storage | In progress — Milestone 4.0 decisions; no runtime change |
| 5 | Higher-quality retrieval | Dense search, sparse search TBD, RRF, reranker | Qdrant, sparse index TBD | Planned |
| 6 | Native image and table understanding | Vision enrichment, multimodal vectors, structured tables | Qdrant, PostgreSQL, object storage | Planned |
| 7 | Measurable quality and reliability | OpenTelemetry-compatible boundary, eval harness, dashboards | Telemetry/eval stores TBD | Planned |
| 8 | Independently scalable deployment | Gateway, API/workers, dedicated frontend TBD, managed services | Managed PostgreSQL, Qdrant, object storage | Planned |
| 9 | Enterprise and commercial controls | Connectors, metering, billing, SSO/SCIM, compliance | PostgreSQL and provider systems | Planned |

## Phase 1 — working prototype

**Status:** Implemented, tagged, and frozen as the V1 recovery baseline.

```mermaid
flowchart LR
    user["User"] -->|"upload PDF"| ui["Streamlit monolith"]
    ui --> files[("Local PDFs, images, artifacts")]
    ui --> parse["PyMuPDF + pdfplumber<br/>Tesseract + Pillow"]
    parse -->|"pages, OCR, tables, images"| langchain["LangChain documents"]
    langchain --> ingest["Chunk + metadata + embeddings"]
    ingest --> openai["OpenAI"]
    ingest --> qdrant[("Qdrant dense vectors")]
    user -->|"question"| ui
    ui --> retrieve["Dense retriever + filters"]
    retrieve --> qdrant
    qdrant --> generate["Grounded multimodal generation"]
    generate --> openai
    openai -->|"answer"| generate
    generate -->|"answer + source/page citations"| ui
```

Actions: parse text/OCR/tables/images, index dense vectors, retrieve by filters,
generate an answer, and show citations. Constraints: the UI directly orchestrates
the pipeline; identity, relational metadata, durable chat, jobs, and production
telemetry do not exist. Phase 2 preserves the proven RAG behavior while adding
product and security boundaries.

## Phase 2 — secure product foundation

**Status:** Completed and accepted. Milestones 2.0.0–2.5, live multimodal model
acceptance, and authenticated visual review pass; the merged release is tagged
`mm-rag-v2.0.0`.

```mermaid
flowchart LR
    user["User"] --> st["Multipage Streamlit product<br/>Overview · Library · Ask · Activity · Settings"]
    st <-->|"login/logout"| idp["Auth0 OIDC<br/>configured and live-validated"]
    st -->|"token + API request"| routes["FastAPI /api/v1<br/>implemented"]
    routes --> authn["RS256 JWT + identity mapping<br/>implemented"]
    authn --> idp
    authn --> authz["Workspace membership guard<br/>implemented; action policy expands later"]
    authz <-->|"identity, documents, conversations, audit activity"| pg[("PostgreSQL<br/>schema at 20260830_0005")]
    authz --> services["Application services"]
    services --> repos["Repositories / gateways"]
    repos --> pg
    repos -->|"trusted tenant/workspace/document/version filters"| qd[("Qdrant<br/>scoped chunks and keyword indexes")]
    repos --> files[("Path-safe local storage adapter<br/>implemented; object storage in Phase 3")]
    services -->|"extract/chunk/embed; retrieve/generate"| openai["OpenAI<br/>backend-only model boundary"]
    health["Live + readiness APIs<br/>implemented"] --> pg
    health --> qd
    routes --> health
    services -->|"atomic safe action metadata"| audit["Immutable activity service"]
    audit --> pg
```

Phase actions: preserve/isolate V1; establish Python/Docker/configuration; add
FastAPI, logs, database pooling, Alembic, health APIs, Auth0/OIDC users and
workspaces; then add multi-document metadata and scoped vectors, backend-mediated RAG,
persistent conversations, multipage Streamlit, CI, negative tenant tests, and
demo hardening.

## Phase 3 — asynchronous ingestion and object storage

**Status:** Completed and accepted.
Migrations through `20260830_0008` implement durable jobs, fenced attempts,
transactional outbox events, immutable generations, and the active-generation
pointer. The streamed HTTP 202 intake, status/cancel/successor-retry API and UX,
confirmed RabbitMQ dispatcher, quorum queue/DLQ, fenced worker, heartbeat/recovery,
generation-aware Qdrant writes/retrieval, and SeaweedFS artifacts are connected.
The deterministic and local-service evidence is complete. One explicitly approved
signed-in real-OpenAI browser proof reached first-attempt immutable promotion and
returned a persisted grounded answer with a citation to that active generation.

```mermaid
flowchart LR
    client["Authorized client"] -->|"streamed upload + Idempotency-Key"| api["Async document API"]
    api --> policy["Workspace policy<br/>implemented"]
    policy -->|"verified immutable original"| objects[("S3 adapter + SeaweedFS local/CI<br/>Implemented and live-tested ADR 0011")]
    policy -->|"document version + job + event"| pg[("PostgreSQL authority<br/>implemented at 20260830_0008")]
    api -->|"HTTP 202 + stable job ID"| client
    pg --> outbox["Transactional outbox + dispatcher<br/>Implemented ADR 0009"]
    outbox --> queue["RabbitMQ quorum queue + DLQ<br/>Implemented ADR 0010"]
    queue --> worker["Fenced Python ingestion worker<br/>Implemented ADR 0012"]
    worker --> objects
    worker --> parse["Parse, OCR, extract"]
    parse --> enrich["Chunk, enrich, embed"]
    enrich -->|"attempt-scoped generation"| qdrant[("Qdrant")]
    enrich -->|"immutable manifest/artifacts"| objects
    worker -->|"progress, heartbeat, fenced promotion"| pg
    pg -->|"retry outbox event"| outbox
    queue -->|"attempts exhausted"| dead["Failed/dead-letter state"]
    client -->|"authorized status request"| api
    api --> pg
```

The API acknowledges quickly after the original and database transaction are durable.
The dispatcher publishes outside the request; workers treat messages as untrusted
wake-ups and reload/fence PostgreSQL state. A validated immutable generation becomes
visible through one active pointer, so failure or cancellation cannot expose partial
vectors. Aggregate operations, retention preview, process health, a representative
large upload, and a temporary PostgreSQL restore exercise complete Milestone 3.5's
free hardening evidence. The signed-in acceptance proof additionally verifies the
live embedding, promotion, active-generation retrieval, citation, and persistence path.

## Phase 4 — fine-grained authorization and governance

**Status:** In progress at Milestone 4.0 decision kickoff. Phase 2 starts isolation;
this phase deepens it. The proposed contracts below are not implemented behavior.

The review source is the
[Phase 4 policy matrix and threat model](PHASE4_POLICY_THREAT_MODEL.md). ADRs
0013–0017 remain Proposed until their approval points are resolved.

```mermaid
flowchart LR
    client["Authenticated client"] --> api["FastAPI"]
    api --> jwt["JWT validation"]
    jwt --> identity["Internal identity"]
    identity --> policy["Workspace RBAC + resource ACL"]
    policy <-->|"membership, ownership, sharing"| pg[("PostgreSQL")]
    policy -->|"allow + trusted scope"| service["Application service"]
    policy -->|"deny"| denied["403 + audit"]
    service -->|"tenant-scoped SQL"| rls["PostgreSQL RLS<br/>defense in depth"]
    rls --> pg
    service -->|"mandatory scope filter"| qdrant[("Qdrant")]
    service -->|"short-lived signed access"| objects[("Object storage")]
    jwt --> audit["Audit event"]
    policy --> audit
    service --> audit
    audit --> pg
    pg --> compliance["Review, retention, export"]
```

Backend-resolved identity and policy govern SQL, vectors, objects, citations,
conversations, and jobs. Negative tests must prove cross-tenant access fails.
Audit events record actor, action, resource, workspace, result, correlation ID,
and time without storing secrets or sensitive content.

## Phase 5 — hybrid retrieval, fusion, and reranking

**Status:** Planned. Sparse and reranking technologies require evaluation.

```mermaid
flowchart LR
    question["Authorized question + scope"] --> prep["Normalize query / intent"]
    prep --> filter["Trusted authorization filter"]
    filter --> dense["Dense semantic retrieval"]
    filter --> sparse["Sparse lexical retrieval<br/>TBD"]
    dense --> qdrant[("Qdrant")]
    sparse --> sindex[("Sparse index TBD")]
    qdrant --> fusion["RRF / evaluated fusion"]
    sindex --> fusion
    fusion --> dedupe["Deduplicate + diversify"]
    dedupe --> rerank["Bounded reranker"]
    rerank --> context["Token-budgeted evidence"]
    context --> generation["Grounded generation"]
    generation --> answer["Answer + ranked citations"]
    question -.-> evaluation["Retrieval evaluation"]
    fusion -.-> evaluation
    rerank -.-> evaluation
```

Authorization applies before every search. Evaluate Recall@k, MRR/nDCG,
groundedness, citation correctness, latency, and cost. Exit: the hybrid pipeline
measurably beats dense-only retrieval without weakening isolation or citations.

## Phase 6 — visual and table intelligence

**Status:** Planned. Models and structured-table technology are TBD.

```mermaid
flowchart LR
    page["Parsed page"] --> classify["Content classifier"]
    classify --> text["Text / OCR path"]
    classify --> image["Image / figure path"]
    classify --> table["Table path"]
    text --> chunks["Text + layout metadata"]
    image --> crop["High-quality crop / render"]
    crop --> vision["Caption + OCR + visual summary"]
    vision --> ivec["Multimodal embedding"]
    table --> structure["Cell/structure reconstruction"]
    structure --> validate["Schema/type validation"]
    validate --> tsummary["Table summary + index form"]
    chunks --> qdrant[("Qdrant multivectors")]
    ivec --> qdrant
    tsummary --> qdrant
    crop --> objects[("Object storage")]
    structure --> pg[("Structured table metadata")]
    query["Question"] --> route["Modality-aware router"]
    route --> qdrant
    route -->|"exact lookup / calculation"| pg
    qdrant --> evidence["Evidence assembler"]
    pg --> evidence
    objects --> evidence
    evidence --> answer["Multimodal answer + exact citations"]
```

Every crop, cell, summary, and vector retains document-version, page, bounding
box, content ID, and extractor-version provenance. Exact calculations use
validated structure, not generated prose. Exit: figures and tables become
first-class retrievable, inspectable, and correctly cited evidence.

## Phase 7 — evaluation and observability

**Status:** Planned. Use a vendor-neutral telemetry boundary where practical.

```mermaid
flowchart TB
    users["Production users"] --> app["Frontend + API + workers"]
    app --> telemetry["OpenTelemetry-compatible instrumentation"]
    telemetry --> logs["Structured logs"]
    telemetry --> traces["Distributed traces"]
    telemetry --> metrics["Latency, errors, throughput, cost"]
    logs --> backend["Observability backend TBD"]
    traces --> backend
    metrics --> backend
    backend --> dashboards["SLO / cost dashboards"]
    dashboards --> alerts["Alerts + runbooks"]
    users --> feedback["User feedback"]
    app --> samples["Privacy-controlled samples"]
    feedback --> evals[("Versioned evaluation datasets")]
    samples --> review["Human review"]
    review --> evals
    candidate["Prompt/parser/retrieval/model candidate"] --> offline["Offline evaluation"]
    evals --> offline
    offline --> gates["Quality + latency + cost + safety gates"]
    gates -->|"pass"| cicd["CI/CD promotion"]
    gates -->|"fail"| candidate
    cicd --> app
    backend -->|"incident learning"| evals
```

Propagate a correlation/trace ID across UI, API, jobs, retrieval, models, and
stores. Do not log tokens, secrets, raw documents, or unreviewed sensitive
content. Exit: the team can explain requests, detect failures, compare RAG
changes before release, and manage reliability, quality, latency, and cost.

## Phase 8 — scalable production platform

**Status:** Planned. Cloud, orchestration, and frontend framework are TBD.

```mermaid
flowchart TB
    user["Users"] --> edge["DNS + TLS + CDN / edge"]
    edge --> web["Dedicated frontend<br/>framework TBD"]
    web --> gateway["Gateway / WAF / rate limiting"]
    gateway --> api["Stateless FastAPI replicas"]
    api --> oidc["OIDC provider"]
    api --> pg[("Managed PostgreSQL<br/>HA + backup + PITR")]
    api --> qd[("Managed / clustered Qdrant")]
    api --> objects[("Managed object storage")]
    api --> queue["Managed queue"]
    queue --> workers["Autoscaled workers"]
    workers --> pg
    workers --> qd
    workers --> objects
    api --> models["Model providers"]
    workers --> models
    secrets["Secrets / key management"] -.-> api
    secrets -.-> workers
    deploy["CI/CD + registry + migrations"] -.-> web
    deploy -.-> api
    deploy -.-> workers
    api -.-> observe["Telemetry + SLOs + alerts"]
    workers -.-> observe
    pg -.-> recovery["Backup / restore / disaster recovery"]
    qd -.-> recovery
    objects -.-> recovery
```

Frontend, API, and workers deploy and scale independently; durable state remains
in managed services. Timeouts, backpressure, graceful shutdown, reversible
releases, and tested restoration are mandatory. Microservices or multi-region
deployment require measured scale, reliability, ownership, or regulatory need.

## Phase 9 — enterprise integrations and commercial controls

**Status:** Planned. Connector and billing providers are TBD.

```mermaid
flowchart LR
    directory["Enterprise SSO / SCIM"] --> identity["Identity + provisioning"]
    admins["Tenant / platform admins"] --> admin["Admin console"]
    systems["Drive, SharePoint, Box, web, APIs"] --> connectors["Connector framework"]
    connectors --> sync["Incremental sync + checkpoints + deletions"]
    sync --> ingestion["Governed ingestion"]
    identity --> policy["Tenant policy + entitlements"]
    admin --> policy
    policy --> product["RAG product APIs"]
    ingestion --> product
    product --> meter["Usage metering"]
    meter --> quota["Quota enforcement"]
    quota --> product
    meter --> ledger[("Immutable usage ledger")]
    ledger --> billing["Billing / subscription provider TBD"]
    product --> audit["Audit / compliance event stream"]
    connectors --> audit
    identity --> audit
    audit --> lifecycle["Retention, legal hold, export, deletion"]
    admin --> reports["Usage, security, compliance, cost reports"]
    ledger --> reports
    lifecycle --> reports
    billing --> reports
```

Connector credentials are tenant-isolated, least-privilege, rotated, and
revocable. Source permissions and deletions propagate into search. Metering is
immutable and quota enforcement is concurrency-safe. Subscription, entitlement,
and usage accounting remain separate. Exit: enterprises can provision users,
connect governed sources, control/audit usage, apply lifecycle policy, and
reconcile commercial usage.

## Architecture invariants

- FastAPI, never the frontend, is the authorization boundary.
- Tenant/workspace filters come only from authenticated backend context.
- PostgreSQL owns relational truth; Qdrant owns vectors/search payload; object
  storage owns original and derived binaries.
- Stable UUIDs and explicit document/index versions replace filenames as identity.
- Ingestion is idempotent, retryable, observable, and safe to resume.
- Repository/gateway interfaces isolate databases, storage, search, identity,
  and model providers from application services.
- Every answer is traceable to authorized source/page evidence.
- Alembic versions database schema; versioned routes protect API evolution.
- Security, accessibility, testing, telemetry, cost, and failure behavior apply
  in every phase.
- A modular monolith remains the default until evidence justifies another service.

## Open technology decisions

| Topic | Current position |
| --- | --- |
| Phase 2 UI | Streamlit multipage application |
| Dedicated Phase 8 UI | Candidate only; framework not selected |
| Queue / broker | Open-source RabbitMQ quorum queue/DLQ implemented under ADR 0010; production hosting deferred |
| Object storage | S3-compatible adapter plus open-source SeaweedFS local/CI implemented under ADR 0011; production provider deferred |
| Transactional outbox | PostgreSQL events plus confirmed leased dispatcher, retry/alert/retention operations implemented under ADR 0009 |
| Worker runtime | Purpose-built Python dispatcher/worker implemented under ADR 0012; one in-flight job per process |
| Fine-grained authorization | Proposed central RBAC ceiling plus optional positive user ACLs under ADR 0013 |
| PostgreSQL tenant defense | Proposed RLS beneath application policy under ADR 0014 |
| Vector/object/async policy | Proposed trusted PostgreSQL scope compilation under ADR 0015 |
| Security audit/export | Proposed append-only PostgreSQL security events under ADR 0016 |
| Retention/deletion | Proposed tombstone-first durable lifecycle under ADR 0017; destructive cleanup remains disabled |
| Sparse search | Required in Phase 5; engine not selected |
| Observability backend | OpenTelemetry-compatible boundary; vendor not selected |
| Deployment platform | Containerized and horizontally scalable; provider not selected |

Accepted Phase 2 decisions are recorded in
[`docs/architecture/decisions`](decisions/):

- [ADR 0001 — Auth0 through OpenID Connect](decisions/0001-auth0-oidc.md)
- [ADR 0002 — Initial workspace role model](decisions/0002-workspace-roles.md)
- [ADR 0003 — Local storage behind an object-storage interface](decisions/0003-local-storage-adapter.md)
- [ADR 0004 — Workspace-scoped document library and vector identity](decisions/0004-document-library-tenancy.md)
- [ADR 0005 — Backend-mediated RAG and scoped persistent conversations](decisions/0005-backend-rag-conversations.md)
- [ADR 0006 — Immutable workspace activity and automated release gates](decisions/0006-audit-and-release-gates.md)

Accepted Phase 3 decisions are:

- [ADR 0007 — Durable ingestion job and attempt state contract](decisions/0007-durable-ingestion-job-attempt-contract.md)
- [ADR 0008 — Ingestion idempotency and immutable output promotion](decisions/0008-ingestion-idempotency-output-promotion.md)
- [ADR 0009 — Transactional outbox dispatch and recovery boundary](decisions/0009-transactional-outbox-dispatch-boundary.md)
- [ADR 0010 — RabbitMQ ingestion broker](decisions/0010-rabbitmq-ingestion-broker.md)
- [ADR 0011 — S3-compatible object storage with SeaweedFS for local development](decisions/0011-s3-compatible-object-storage-seaweedfs.md)
- [ADR 0012 — Purpose-built Python dispatcher and ingestion worker runtime](decisions/0012-python-dispatcher-worker-runtime.md)

Proposed Phase 4 decisions awaiting review are:

- [ADR 0013 — Central RBAC and resource ACL policy](decisions/0013-central-rbac-resource-acl-policy.md)
- [ADR 0014 — PostgreSQL row-level-security defense](decisions/0014-postgresql-row-level-security.md)
- [ADR 0015 — Authorized vector, object, and asynchronous access](decisions/0015-authorized-vector-object-async-access.md)
- [ADR 0016 — Security audit and compliance export](decisions/0016-security-audit-compliance-export.md)
- [ADR 0017 — Governed retention, deletion, encryption, and incident controls](decisions/0017-governed-retention-deletion-incident-controls.md)

## Maintenance checklist

1. Update the affected phase, diagram, status, and technology table.
2. Update the whole-system diagram when a cross-phase boundary or flow changes.
3. Record consequential Phase 4 decisions and rationale in the ignored
   `Phase4_context.md` active context document; keep `Phase3_context.md` historical.
4. Keep unapproved technologies labeled **Proposed / TBD**.
5. Verify Mermaid fences and links before committing.
6. Never place credentials, tokens, private URLs, customer data, or other secrets
   in this version-controlled document.
