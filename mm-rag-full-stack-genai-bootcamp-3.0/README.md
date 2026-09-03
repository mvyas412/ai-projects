# Multimodal RAG Production — Phase 6 visual and table intelligence

Phase 3 evolves the accepted secure product foundation into durable asynchronous
ingestion backed by object storage and independently scalable workers. V1 and V2
remain unchanged at the immutable `mm-rag-v1.0.0` and `mm-rag-v2.0.0` Git tags.

## Current status

Phase 3 is accepted and preserved at `mm-rag-v3.0.0`. Phase 4 Milestones 4.0–4.5
are completed and accepted: implementation PR #3 and closure PR #4 were
squash-merged, and the accepted lineage is preserved by annotated tag
`mm-rag-v4.0.0` at `996898e`.
ADRs 0013–0017 are accepted and migrations through `20260831_0013` add central
default-deny policy,
tenant-constrained ACLs, PostgreSQL RLS, cross-store authorization, safe append-only
security review, checksummed compliance export, and durable tombstone-first lifecycle
plans. Qdrant access requires bounded trusted scope, object access is backend-mediated
and integrity-checked, and retention apply fails closed unless an exact owner-approved
preview remains current. No automatic destructive retention schedule is enabled.
Phase 5 implementation is complete and closed without quality acceptance. PR #5
was squash-merged into `main` at `5436614` with a tree identical to the reviewed
source; no Phase 5 release tag was created. The v1
through v4 paid candidates all stopped at validation. The single approved v4 attempt on 2026-09-02
used one 2,545-token embedding batch and passed the ceiling-aware Recall, MRR,
class, identity, latency, and provider-call gates. Its nDCG@10 improved from
`0.8439` to `0.8632`, a 2.28% relative gain against the required 5%. The runner
correctly withheld holdout and the end-to-end proof. Accepted ADR 0024 keeps that
5% standard and its tune-only `hybrid-v3` candidate unchanged: ordinary queries
retain dense order, while exact and multi-intent syntax selects balanced hybrid
retrieval plus the pinned local reranker. The v4 approval is consumed; no retry or
profile promotion is authorized. The user approved ending Phase 5 without another
remediation cycle; `hybrid-v3` remains evaluation-only. The free gate passes 198
deterministic tests plus all 209 live tests, pinned model verification, and v4 fixture
reproduction. The default
`hybrid-v1` profile combines authorized dense and Qdrant-native BM25 legs through
deterministic RRF;
`dense-v1` remains the rollback path, and `hybrid-rerank-v1` remains opt-in until
measured evidence proves the bounded local cross-encoder improves quality.

The current `3.0` lineage contains:

- The verified V1 parsing, ingestion, retrieval, generation, and Streamlit flow.
- A dedicated Python 3.12 environment managed by uv.
- Locked runtime and development dependencies.
- Isolated local PostgreSQL, Qdrant, and SeaweedFS service definitions.
- Environment and Streamlit configuration boundaries.
- A modular FastAPI application factory and versioned API router.
- Structured request logs with correlation IDs.
- A pooled SQLAlchemy/psycopg PostgreSQL connection layer.
- Alembic migration infrastructure and a reversible baseline revision.
- Independent liveness and dependency-aware readiness endpoints.
- Auth0/OIDC access-token validation with strict issuer, audience, signature,
  issued-at, expiration, and subject checks.
- PostgreSQL users, workspaces, memberships, and owner provisioning through
  Alembic revision `20260829_0002`.
- Protected current-user and workspace APIs with non-enumerating membership checks.
- Provider-neutral local and S3-compatible object-storage adapters with streamed
  I/O, checksum/size metadata, conditional immutable creation, safe error mapping,
  and opaque workspace/document/version object keys.
- A live-tested open-source SeaweedFS local/CI provider with restart persistence;
  Amazon S3 remains an unprovisioned future production option.
- A separate authenticated Streamlit shell.
- Synchronous text, PDF, DOCX, and image-description indexing behind a replaceable
  document-indexer boundary, with mandatory workspace/document/version vector scope.
- Persistent workspace-, collection-, or document-scoped conversations with
  backend-mediated retrieval, answer generation, and structured citations.
- Immutable dense-and-sparse successor generations, identical trusted Qdrant filters
  on both retrieval legs, deterministic RRF/deduplication/diversification, and
  content-free candidate traces with safe dense fallback.
- A pinned, checksum-verified offline FastEmbed BM25 model and optional local ONNX
  cross-encoder, provisioned at setup/image-build time and never in a request path.
- Reproducible hashed v2/v3 diagnostics and v4 candidate benchmark. V4 contains
  120 chunks and 80 balanced queries with protected 48/16/16 splits, class-level
  gates, validation-before-holdout execution, a frozen selector fingerprint, and
  an explicit paid runner whose raw results remain Git-ignored.
- A presentation-focused native Streamlit experience with top navigation,
  workspace switching, document/collection management, persistent chat,
  evidence inspection, first-document guidance, downloads, settings, and
  coordinated light/dark themes.
- Auth0 profile claims are presented consistently in the sidebar, Settings, and
  current-user activity while tokens remain outside Session State.
- Immutable workspace activity records and an authorized, presentation-safe
  Activity page that suppresses internal identifiers.
- Provider-neutral durable ingestion jobs and fenced execution attempts in
  PostgreSQL, with idempotent creation, workspace-scoped control, three-attempt
  budgets, leases, progress, cancellation, retry, and expired-lease recovery.
- A PostgreSQL transactional outbox at migration `20260830_0007`, with atomic
  initial/retry dispatch intents, minimal versioned payloads, strict per-job
  ordering, expiring dispatcher leases, safe backoff metadata, and acknowledgement
  or discard transitions.
- Migration `20260830_0008`, immutable attempt-scoped output generations, verified
  manifests, and a fenced PostgreSQL active-generation promotion boundary.
- A free local RabbitMQ quorum queue and dead-letter queue, confirmed transactional-
  outbox dispatcher, manual-ack/prefetch-1 worker, heartbeats, lease recovery,
  retry/backoff, cancellation checkpoints, process health, and graceful shutdown.
- Streamed asynchronous upload returning HTTP 202 and a stable job ID, authorized
  status/list/cancel/successor-retry APIs, and Streamlit progress/control UX.
- Aggregate non-disclosing operations, safe 30-day terminal-outbox retention,
  representative large-upload coverage, and an exercised PostgreSQL backup/restore.
- GitHub Actions quality, typing, migration, live-service, test, and coverage gates.
- Automated environment, backend, tenant-isolation, storage, and Streamlit tests.
- An isolated real-OpenAI acceptance command covering text and image indexing,
  scoped retrieval, grounded citations, persistence, audit, and tenant isolation.

This directory starts from the accepted V2 tree. Phase 3 Milestones 3.0–3.5 are
implemented and accepted, including one explicitly approved signed-in live-model
asynchronous upload, immutable promotion, retrieval, citation, and persistence proof.
Accepted ADRs 0007 and 0008 define the durable job/attempt and idempotent output-
promotion contracts. The provider-neutral job/attempt persistence and state machine
are connected to the asynchronous upload and indexing path.
ADR 0009's provider-neutral transactional-outbox boundary is now implemented.
ADRs 0010–0012
select free self-hosted RabbitMQ, an S3-compatible adapter with open-source SeaweedFS
for local/CI, and separate purpose-built Python dispatcher/worker processes. The S3
adapter, immutable key contract, SeaweedFS Compose service, provider contract tests,
outbox persistence/recovery contract, RabbitMQ topology, dispatcher/worker runtime,
immutable generation promotion, asynchronous API, and progress UX are implemented.
The deterministic and free live-service gates cover these boundaries; paid OpenAI
acceptance is never run implicitly or repeated without explicit authorization.

## Architecture and roadmap

The living [architecture handbook](docs/architecture/ARCHITECTURE.md) contains:

- The whole-system target architecture and end-to-end data flows.
- A focused component and interaction diagram for every phase from 1 through 9.
- Current implementation status, architecture invariants, open technology
  decisions, and documentation-maintenance rules.

The accepted [Phase 4 policy matrix and threat model](docs/architecture/PHASE4_POLICY_THREAT_MODEL.md)
defines the implemented contract for roles, resource visibility, ACL inheritance,
trust boundaries, cross-store authorization, audit, and lifecycle safety.

Planned components are explicitly labeled so the diagrams do not imply that
future capabilities have already been implemented.

The [architecture poster gallery](docs/architecture/ARCHITECTURE_POSTERS.md)
provides presentation-ready whole-system, final-production, and Phase 1–9 images.
The [current workflow and DEV architecture](docs/architecture/current/mm-rag-current-workflow-dev-architecture.svg)
shows the Phase 5 implementation checkpoint, including hybrid retrieval and the
failed v4 paid nDCG gate. Phase 5 is closed without candidate promotion. Phase 6
decision kickoff PR #6 was squash-merged at `95d18b3`, and ADRs 0025–0030 were
accepted on 2026-09-03. Implementation has not started, so the current poster remains
the accurate runtime checkpoint.

The living [project plan](docs/PROJECT_PLAN.md) defines the Phase 1–9 delivery
sequence, milestones, dependencies, completion gates, risks, decision backlog,
and current next actions. Update it with evidence whenever progress or scope changes.
Use the [Phase 3 operations runbook](docs/PHASE3_OPERATIONS.md) for ingestion runtime
health, alerts, and lease recovery. Use the [Phase 4 governance operations runbook](docs/PHASE4_GOVERNANCE_OPERATIONS.md)
for retention preview/apply, blocked-plan recovery, encryption posture, incident
response, and backup/restore exercises.

Accepted decisions are recorded as ADRs:

- [Auth0 through OIDC](docs/architecture/decisions/0001-auth0-oidc.md)
- [Workspace roles](docs/architecture/decisions/0002-workspace-roles.md)
- [Local storage adapter](docs/architecture/decisions/0003-local-storage-adapter.md)
- [Workspace-scoped document library](docs/architecture/decisions/0004-document-library-tenancy.md)
- [Backend-mediated conversations and RAG](docs/architecture/decisions/0005-backend-rag-conversations.md)
- [Workspace activity and release gates](docs/architecture/decisions/0006-audit-and-release-gates.md)
- [Durable ingestion job and attempt state contract](docs/architecture/decisions/0007-durable-ingestion-job-attempt-contract.md)
- [Ingestion idempotency and immutable output promotion](docs/architecture/decisions/0008-ingestion-idempotency-output-promotion.md)
- [Transactional outbox dispatch and recovery boundary](docs/architecture/decisions/0009-transactional-outbox-dispatch-boundary.md)
- [RabbitMQ ingestion broker](docs/architecture/decisions/0010-rabbitmq-ingestion-broker.md)
- [S3-compatible object storage with SeaweedFS for local development](docs/architecture/decisions/0011-s3-compatible-object-storage-seaweedfs.md)
- [Purpose-built Python dispatcher and ingestion worker runtime](docs/architecture/decisions/0012-python-dispatcher-worker-runtime.md)

Accepted Phase 4 decisions are:

- [Central RBAC and resource ACL policy](docs/architecture/decisions/0013-central-rbac-resource-acl-policy.md)
- [PostgreSQL row-level-security defense](docs/architecture/decisions/0014-postgresql-row-level-security.md)
- [Authorized vector, object, and asynchronous access](docs/architecture/decisions/0015-authorized-vector-object-async-access.md)
- [Security audit and compliance export](docs/architecture/decisions/0016-security-audit-compliance-export.md)
- [Governed retention, deletion, encryption, and incident controls](docs/architecture/decisions/0017-governed-retention-deletion-incident-controls.md)

Accepted Phase 5 decisions are:

- [Versioned retrieval evaluation and dense baseline](docs/architecture/decisions/0018-retrieval-evaluation-dense-baseline.md)
- [Qdrant-native sparse retrieval](docs/architecture/decisions/0019-qdrant-sparse-bm25-retrieval.md)
- [Deterministic reciprocal-rank fusion](docs/architecture/decisions/0020-deterministic-rrf-fusion.md)
- [Bounded local cross-encoder reranking](docs/architecture/decisions/0021-bounded-local-reranking.md)
- [Phase 5 benchmark remediation and negative-query contract](docs/architecture/decisions/0022-phase5-benchmark-remediation.md)
- [Ceiling-aware retrieval quality and deterministic candidate selection](docs/architecture/decisions/0023-ceiling-aware-quality-and-candidate-selection.md)
- [Adaptive retrieval and fresh protected evidence](docs/architecture/decisions/0024-adaptive-retrieval-and-fresh-protected-evidence.md)

Accepted Phase 6 decisions are:

- [Visual and table evaluation contract](docs/architecture/decisions/0025-phase6-visual-table-evaluation-contract.md)
- [Immutable region and derived-artifact provenance](docs/architecture/decisions/0026-immutable-region-artifact-provenance.md)
- [Local-first visual extraction and enrichment](docs/architecture/decisions/0027-local-first-visual-extraction-enrichment.md)
- [Visual embeddings, indexing, and modality-aware retrieval](docs/architecture/decisions/0028-visual-embedding-index-retrieval.md)
- [Structured tables and safe exact calculation](docs/architecture/decisions/0029-structured-tables-safe-calculation.md)
- [Region evidence, viewer, and Phase 6 rollout](docs/architecture/decisions/0030-region-evidence-viewer-rollout.md)

These ADRs authorize implementation in milestone order, beginning with the free
evaluation contract. Exact artifacts remain subject to pinned revision, license,
checksum, and measured acceptance requirements. Provider calls, paid evaluation,
profile promotion, and a release tag still require their separate explicit gates.

## Prerequisites

- [uv](https://docs.astral.sh/uv/)
- Python 3.12, installed directly or managed by uv
- Tesseract OCR with the English language data
- Docker Desktop or another Compose-compatible container runtime for local
  PostgreSQL, Qdrant, SeaweedFS, and RabbitMQ.

## Create the dedicated environment

Run all commands from this `3.0` directory:

```bash
uv python install 3.12
uv sync
```

`uv sync` creates an ignored `.venv/` beside `pyproject.toml` and installs the
exact versions recorded in `uv.lock`. There is no need to activate the virtual
environment when commands are run with `uv run`.

Confirm the interpreter is isolated from V1:

```bash
uv run python -c "import sys; print(sys.executable)"
```

The printed path must be inside this directory's `.venv/`.

## Configure local settings

Create a local configuration file and replace placeholder credentials:

```bash
cp .env.example .env
```

Never commit `.env`, `.streamlit/secrets.toml`, private keys, credentials,
uploaded documents, or generated RAG artifacts. The tracked `.env.example`
contains names and safe placeholders only.

The backend owns Auth0 validation settings, OpenAI, PostgreSQL, and Qdrant
credentials. Streamlit receives only its API URL and OIDC client settings.

### Configure Auth0 locally

In Auth0, create a Regular Web Application for Streamlit and an API for FastAPI.
Use the same API audience in both configurations. For local development, allow:

- Callback URL: `http://localhost:8503/oauth2callback`
- Logout URLs: `http://localhost:8503` and
  `http://localhost:8503/oauth2callback`
- Web origin: `http://localhost:8503`

Set `AUTH0_ISSUER` and `AUTH0_AUDIENCE` in ignored `.env`. Then create the
ignored Streamlit secrets file:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Replace every placeholder in that file. `AUTH0_ISSUER` must match the access
token `iss` claim exactly, including its trailing slash. The frontend requests
the configured audience so Auth0 returns an API access token rather than an
opaque user-session token.

## Start PostgreSQL, Qdrant, SeaweedFS, and RabbitMQ

After configuring `.env` and installing a container runtime:

```bash
docker compose up -d
docker compose ps
```

Local endpoints are intentionally separated from V1:

| Component | Endpoint |
| --- | --- |
| Streamlit | `http://127.0.0.1:8503` |
| FastAPI backend | `http://127.0.0.1:8003` |
| PostgreSQL | `127.0.0.1:5434` |
| Qdrant HTTP | `http://127.0.0.1:6337` |
| Qdrant gRPC | `127.0.0.1:6338` |
| SeaweedFS S3 | `http://127.0.0.1:8333` |

| RabbitMQ AMQP | `127.0.0.1:5673` |
| RabbitMQ management | `http://127.0.0.1:15673` |

PostgreSQL, Qdrant, SeaweedFS, and RabbitMQ use Compose-managed Phase 3 volumes. Do not mount
or reuse V1 or V2 runtime data. The example SeaweedFS credentials are localhost-only
development values, not production secrets. Override them in ignored configuration
for any shared environment.

Existing Phase 3 databases continue using `OBJECT_STORAGE_BACKEND=local` until an
explicit object migration is implemented. A clean development environment may set
`OBJECT_STORAGE_BACKEND=s3`; FastAPI then adds `object_storage` to dependency readiness.

Readiness checks:

```bash
docker compose exec postgres pg_isready -U mm_rag -d mm_rag_phase3
curl --fail http://127.0.0.1:6337/readyz
docker compose ps seaweedfs rabbitmq
```

Start or stop the independently packaged execution processes explicitly:

```bash
make runtime
make operations-status
make runtime-stop
```

`make services` does not start the runtime profile, preventing accidental model
work during dependency-only development.

Stop services without deleting their volumes:

```bash
docker compose down
```

Do not add `-v` unless you explicitly intend to delete the Phase 3 PostgreSQL,
Qdrant, SeaweedFS, and RabbitMQ data volumes.

## Apply database migrations

The migration history contains the infrastructure baseline plus identity,
document-library, conversation, immutable activity, durable ingestion-job,
transactional-outbox, immutable-generation, Phase 4 authorization/audit, and governed
lifecycle schemas through `20260831_0013`:

```bash
uv run alembic upgrade head
uv run alembic current
```

All future PostgreSQL schema changes must be created and reviewed as Alembic
revisions. Runtime code and migrations share `backend.app.db.base.Base.metadata`.

## Run and verify the FastAPI backend

Start the backend on its loopback-only development endpoint:

```bash
uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8003
```

API documentation is available at `http://127.0.0.1:8003/docs`.

| Endpoint | Meaning | Response behavior |
| --- | --- | --- |
| `GET /api/v1/health/live` | The API process can respond | HTTP 200 without checking external services |
| `GET /api/v1/health/ready` | PostgreSQL and Qdrant are usable | HTTP 200 when ready; safe HTTP 503 otherwise |
| `GET /api/v1/users/me` | Provision/read the authenticated user and personal workspace | HTTP 200 with valid Auth0 token; 401 otherwise |
| `GET /api/v1/workspaces` | List only the caller's workspaces | HTTP 200 with membership-scoped results |
| `POST /api/v1/workspaces` | Create a workspace owned by the caller | HTTP 201 with an `owner` membership |
| `GET /api/v1/workspaces/{id}` | Read one authorized workspace | HTTP 404 for missing or unauthorized workspace |
| `GET/POST /api/v1/workspaces/{id}/documents` | List or upload workspace documents | Membership-scoped; write roles only for upload |
| `GET/DELETE /api/v1/workspaces/{id}/documents/{document_id}` | Inspect or archive one document | Unauthorized resources remain hidden with HTTP 404 |
| `POST /api/v1/workspaces/{id}/documents/{document_id}/versions` | Add an immutable document version | Duplicate content/config returns HTTP 409 |
| `POST /api/v1/workspaces/{id}/documents/{document_id}/versions/{version_id}/index` | Extract, embed, and index an authorized immutable version | Returns chunk count; safe 503 when model services are unavailable |
| `POST /api/v1/workspaces/{id}/ingestion/uploads` | Stream an immutable original and create a durable job/outbox event | Requires `Idempotency-Key`; returns HTTP 202 and a stable job ID |
| `GET /api/v1/workspaces/{id}/ingestion/jobs` | List authorized durable ingestion status | Bounded, workspace-scoped safe progress |
| `GET /api/v1/workspaces/{id}/ingestion/jobs/{job_id}` | Read one job and latest attempt progress | Unauthorized jobs remain hidden with HTTP 404 |
| `POST /api/v1/workspaces/{id}/ingestion/jobs/{job_id}/cancel` | Cooperatively cancel the member's job | Never promotes output after cancellation wins |
| `POST /api/v1/workspaces/{id}/ingestion/jobs/{job_id}/retry` | Create a successor for a terminal job | Requires a new idempotency key; predecessor stays immutable |
| `GET/POST /api/v1/workspaces/{id}/collections` | List or create collections | Collection names are unique per workspace |
| `PUT/DELETE /api/v1/workspaces/{id}/collections/{collection_id}/documents/{document_id}` | Add or remove a collection document | Both resources must belong to the authorized workspace |
| `GET/POST /api/v1/workspaces/{id}/conversations` | List or create scoped persistent conversations | Targets a workspace, collection, or explicit documents |
| `GET /api/v1/workspaces/{id}/conversations/{conversation_id}` | Resume a conversation with citations | Unauthorized resources remain hidden with HTTP 404 |
| `POST /api/v1/workspaces/{id}/conversations/{conversation_id}/messages` | Ask the backend-mediated RAG assistant | Only READY versions in the trusted target scope can be cited |
| `GET /api/v1/workspaces/{id}/activity` | List recent security-relevant workspace actions | Membership-scoped, bounded, newest-first results |
| `POST /api/v1/workspaces/{id}/governance/{documents\|conversations}/{resource_id}/deletion` | Tombstone a document or conversation and create a recoverable plan | Document purge is owner-only; tombstoned content is hidden immediately |
| `POST /api/v1/workspaces/{id}/governance/{documents\|conversations}/{resource_id}/restore` | Restore a resource during its recoverable window | Held, expired, purging, or terminal plans fail closed |
| `PUT/DELETE /api/v1/workspaces/{id}/governance/holds/{type}/{resource_id}` | Place or remove a retention hold | Owner/admin only; every change is audited |
| `GET /api/v1/workspaces/{id}/governance/retention/preview` | Produce bounded eligible counts and an exact scope token | Read-only and owner-authorized; no deletion occurs |
| `POST /api/v1/workspaces/{id}/governance/retention/apply` | Recompute and apply the exact previewed scope | Owner-only; scope drift, live work, holds, or provider uncertainty block cleanup |

Uploads are bounded by `MAX_UPLOAD_BYTES` (25 MiB by default), streamed through the
path-safe object-storage adapter, and identified by content and ingestion
fingerprints. Vector payloads reserve keyword-indexed `tenant_id`, `workspace_id`,
`document_id`, `document_version_id`, and `generation_id` fields; trusted backend
helpers construct all retrieval filters and resolve the active generation from PostgreSQL.

Verify from another terminal:

```bash
curl --fail http://127.0.0.1:8003/api/v1/health/live
curl --fail http://127.0.0.1:8003/api/v1/health/ready
```

Readiness responses contain only component state and latency. They never expose
connection strings, passwords, API keys, stack traces, or raw dependency errors.

## Run the current Streamlit baseline

```bash
uv run streamlit run ui/app.py
```

The committed `.streamlit/config.toml` assigns Phase 3 port `8503` and disables
usage-statistics collection.

## Run the authenticated application

After completing the Auth0 configuration and starting FastAPI:

```bash
uv run streamlit run frontend/streamlit_app.py
```

The application uses native Streamlit OIDC login, keeps the access token out of
Session State, and routes product operations through protected FastAPI APIs.

- **Overview** summarizes documents, indexed readiness, collections, and recent chat;
  an empty workspace links directly to the expanded Library upload form.
- **Library** streams uploads, follows durable stage/unit progress, cancels or creates
  successor retries, downloads sources, and manages collections.
- **Ask** explains each retrieval scope, creates persistent conversations, and
  opens citation evidence.
- **Activity** presents authorized workspace actions without raw internal IDs.
- **Settings** shows the Auth0 profile, workspace access, and safe service readiness.

The existing `ui/app.py` remains available as the preserved V1 RAG reference.

## Verify the environment

```bash
uv lock --check
uv sync --locked
uv run pytest
uv run ruff check backend frontend migrations tests
uv run mypy backend frontend tests/backend
```

The tests verify Python 3.12, the Phase 3 interpreter path, required imports,
Streamlit startup, configuration, transactions, migrations, liveness,
readiness-success behavior, safe dependency-failure behavior, and the durable
ingestion transition, authorization, idempotency, lease, retry, cancellation,
atomic outbox, ordering, and dispatcher-lease invariants.

With PostgreSQL and Qdrant running, include the live integration check:

```bash
MM_RAG_RUN_INTEGRATION_TESTS=1 uv run pytest tests/backend/test_integration_services.py
```

With SeaweedFS running, its provider contract has a separate explicit flag:

```bash
MM_RAG_RUN_S3_INTEGRATION_TESTS=1 uv run pytest tests/backend/test_s3_integration.py
```

The same gates are available through stable commands:

```bash
make check       # locked dependencies, lint, types, tests, migration head, diff hygiene
make check-live  # also checks live services and the SeaweedFS provider contract
make phase5-evaluation  # validates the free hashed 80-query v4 benchmark contract
make check-acceptance PHASE5_EMBEDDING_COST_USD_PER_MILLION_TOKENS=<current-rate>
```

Run `make check-acceptance` only after fresh explicit approval. The 2026-09-02 v4
authorization has been consumed and does not permit a retry. The command
compares dense-v1, hybrid-v1, hybrid-v2, hybrid-v3, and hybrid-rerank-v1
profiles with one batched paid embedding request. Validation
must pass before holdout retrieval/output and the end-to-end product proof can run. It then exercises
async text/image ingestion, scoped hybrid retrieval, grounded generation, citations,
persistence, audit, and cross-tenant denial. Temporary collections are removed and
raw benchmark identities remain ignored. A failed benchmark gate stops before the
end-to-end product proof and never authorizes an automatic retry.

GitHub Actions runs deterministic and PostgreSQL/Qdrant integration gates on pushes
to the Phase 3, Phase 4, Phase 5, and Phase 6 branches and relevant pull requests. The
SeaweedFS contract remains in the local live gate until CI provisions that
command-based service explicitly.
Coverage must remain at or above 70%.

Use the [demonstration runbook](docs/DEMO_RUNBOOK.md) for preflight, the five-minute
product story, suggested prompts, failure-safe talking points, and visual acceptance.

## Dependency policy

- `pyproject.toml` is the human-maintained dependency source of truth.
- `uv.lock` is generated by uv and records exact direct and transitive versions.
- The `dev` dependency group contains tests, linting, formatting, and typing tools.
- The optional `notebooks` group is installed with `uv sync --group notebooks`.
- Use `uv add` and `uv remove` for dependency changes.
- Do not install project dependencies manually into `.venv`.
- `requirements.txt` is retained temporarily as a V1 migration reference.

## Project structure

```text
.
├── .env.example              # Safe configuration template
├── .python-version           # Supported Python line
├── .streamlit/               # Shareable settings and safe OIDC secrets template
├── alembic.ini               # Migration runner configuration
├── backend/app/              # FastAPI, auth, models, repositories, services, storage
├── compose.yaml              # Dependencies plus explicit dispatcher/worker runtime profile
├── docs/                     # Living project plan, architecture, and ADRs
├── frontend/                 # Authenticated Phase 3 Streamlit shell
├── migrations/               # Versioned PostgreSQL schema changes
├── pyproject.toml            # Dependencies and Python tool configuration
├── scripts/                  # Deterministic and live acceptance commands
├── uv.lock                   # Exact reproducible dependency resolution
├── src/                      # Current RAG implementation
├── ui/app.py                 # Current Streamlit baseline
└── tests/                    # Unit, integration, environment, and smoke tests
```

Phase 2 is merged and recoverable at `mm-rag-v2.0.0`. Phase 3 is implemented,
accepted, and merged into `main` through PR #2 at `228ce63` after the explicitly
authorized real-OpenAI asynchronous browser proof. The immutable accepted release
is tagged `mm-rag-v3.0.0` at `9ebe767`. Phase 4 is completed, accepted, and
squash-merged through PR #3 at `57ee453`; its documentation closure is preserved by
annotated tag `mm-rag-v4.0.0` at `996898e`.
Production providers and deployment remain future Phase 8 decisions.
