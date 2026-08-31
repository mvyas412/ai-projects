# Multimodal RAG Production — Phase 3

Phase 3 evolves the accepted secure product foundation into durable asynchronous
ingestion backed by object storage and independently scalable workers. V1 and V2
remain unchanged at the immutable `mm-rag-v1.0.0` and `mm-rag-v2.0.0` Git tags.

## Current status

The Phase 3 baseline currently contains:

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

Planned components are explicitly labeled so the diagrams do not imply that
future capabilities have already been implemented.

The [architecture poster gallery](docs/architecture/ARCHITECTURE_POSTERS.md)
provides presentation-ready whole-system, final-production, and Phase 1–9 images.
The [current workflow and DEV architecture](docs/architecture/current/mm-rag-current-workflow-dev-architecture.svg)
shows the accepted Phase 3 checkpoint and distinguishes verified current components
from later planned phases.

The living [project plan](docs/PROJECT_PLAN.md) defines the Phase 1–9 delivery
sequence, milestones, dependencies, completion gates, risks, decision backlog,
and current next actions. Update it with evidence whenever progress or scope changes.
Use the [Phase 3 operations runbook](docs/PHASE3_OPERATIONS.md) for runtime health,
alerts, lease recovery, retention, and backup/restore exercises.

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
transactional-outbox, and immutable-generation schemas through `20260830_0008`:

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

## Run the authenticated Phase 3 application

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
make check-acceptance  # also makes paid OpenAI calls in isolated temporary data
```

`make check-acceptance` exercises text and generated-image ingestion, embeddings,
scoped Qdrant retrieval, grounded generation, citations, persistence, audit, and
cross-tenant denial. It removes its temporary SQL, files, and vector collection.

GitHub Actions runs deterministic and PostgreSQL/Qdrant integration gates on pushes
to the Phase 3 branch and relevant pull requests. The SeaweedFS contract remains in
the local live gate until CI provisions that command-based service explicitly.
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
is tagged `mm-rag-v3.0.0` at `9ebe767`. Production providers and deployment remain
future Phase 8 decisions.
