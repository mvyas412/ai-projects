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
- GitHub Actions quality, typing, migration, live-service, test, and coverage gates.
- Automated environment, backend, tenant-isolation, storage, and Streamlit tests.
- An isolated real-OpenAI acceptance command covering text and image indexing,
  scoped retrieval, grounded citations, persistence, audit, and tenant isolation.

This directory starts from the accepted V2 tree. Phase 3 has completed Milestone 3.2
and is entering Milestone 3.3.
Accepted ADRs 0007 and 0008 define the durable job/attempt and idempotent output-
promotion contracts. The provider-neutral job/attempt persistence and state-machine
foundation is implemented but is not connected to the synchronous indexing API.
ADR 0009's provider-neutral transactional-outbox boundary is now implemented.
ADRs 0010–0012
select free self-hosted RabbitMQ, an S3-compatible adapter with open-source SeaweedFS
for local/CI, and separate purpose-built Python dispatcher/worker processes. The S3
adapter, immutable key contract, SeaweedFS Compose service, provider contract tests,
and outbox persistence/recovery contract are implemented. RabbitMQ topology,
dispatcher/worker processes, asynchronous API, and progress UX remain unimplemented,
so no asynchronous behavior is claimed yet.

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
shows the exact Milestone 3.2 checkpoint and distinguishes live,
accepted/pending, and planned components.

The living [project plan](docs/PROJECT_PLAN.md) defines the Phase 1–9 delivery
sequence, milestones, dependencies, completion gates, risks, decision backlog,
and current next actions. Update it with evidence whenever progress or scope changes.

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
  PostgreSQL, Qdrant, and SeaweedFS. RabbitMQ joins the stack in Milestone 3.3.

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

## Start PostgreSQL, Qdrant, and SeaweedFS

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

PostgreSQL, Qdrant, and SeaweedFS use Compose-managed Phase 3 volumes. Do not mount
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
docker compose ps seaweedfs
```

Stop services without deleting their volumes:

```bash
docker compose down
```

Do not add `-v` unless you explicitly intend to delete the Phase 3 PostgreSQL,
Qdrant, and SeaweedFS data volumes.

## Apply database migrations

The migration history contains the infrastructure baseline plus identity,
document-library, conversation, immutable activity, durable ingestion-job, and
transactional-outbox schemas through `20260830_0007`:

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
| `GET/POST /api/v1/workspaces/{id}/collections` | List or create collections | Collection names are unique per workspace |
| `PUT/DELETE /api/v1/workspaces/{id}/collections/{collection_id}/documents/{document_id}` | Add or remove a collection document | Both resources must belong to the authorized workspace |
| `GET/POST /api/v1/workspaces/{id}/conversations` | List or create scoped persistent conversations | Targets a workspace, collection, or explicit documents |
| `GET /api/v1/workspaces/{id}/conversations/{conversation_id}` | Resume a conversation with citations | Unauthorized resources remain hidden with HTTP 404 |
| `POST /api/v1/workspaces/{id}/conversations/{conversation_id}/messages` | Ask the backend-mediated RAG assistant | Only READY versions in the trusted target scope can be cited |
| `GET /api/v1/workspaces/{id}/activity` | List recent security-relevant workspace actions | Membership-scoped, bounded, newest-first results |

Uploads are bounded by `MAX_UPLOAD_BYTES` (25 MiB by default), stored through the
path-safe object-storage adapter, and identified by content and ingestion
fingerprints. Vector payloads reserve keyword-indexed `tenant_id`, `workspace_id`,
`document_id`, and `document_version_id` fields; trusted backend helpers construct
all retrieval filters.

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
- **Library** uploads/downloads sources, starts indexing, and manages collections.
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
├── compose.yaml              # Isolated Phase 3 PostgreSQL, Qdrant, and SeaweedFS
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

Phase 2 is merged and recoverable at `mm-rag-v2.0.0`. The active next step is
Milestone 3.3: add the accepted RabbitMQ topology and confirmed outbox dispatcher,
then the fenced ingestion-worker runtime. The synchronous product path remains active
until the later asynchronous API and UX milestone passes its acceptance gate.
