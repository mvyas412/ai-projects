# Multimodal RAG Production — Phase 2

Phase 2 evolves the working multimodal RAG prototype into a reproducible,
secure, tenant-aware, and presentation-quality application. The V1 application
remains unchanged in the sibling `mm-rag-full-stack-genai-bootcamp-1.0/`
directory and at the immutable `mm-rag-v1.0.0` Git tag.

## Current status

The Phase 2 branch currently contains:

- The verified V1 parsing, ingestion, retrieval, generation, and Streamlit flow.
- A dedicated Python 3.12 environment managed by uv.
- Locked runtime and development dependencies.
- Isolated local PostgreSQL and Qdrant service definitions.
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
- A path-safe local object-storage adapter and separate authenticated Streamlit shell.
- Automated environment, backend, tenant-isolation, storage, and Streamlit tests.

Live Auth0 login requires environment-specific tenant credentials. Multi-document
metadata, collections, retrieval filters, and persistent conversations remain the
next product slices.

## Architecture and roadmap

The living [architecture handbook](docs/architecture/ARCHITECTURE.md) contains:

- The whole-system target architecture and end-to-end data flows.
- A focused component and interaction diagram for every phase from 1 through 9.
- Current implementation status, architecture invariants, open technology
  decisions, and documentation-maintenance rules.

Planned components are explicitly labeled so the diagrams do not imply that
future capabilities have already been implemented.

The living [project plan](docs/PROJECT_PLAN.md) defines the Phase 1–9 delivery
sequence, milestones, dependencies, completion gates, risks, decision backlog,
and current next actions. Update it with evidence whenever progress or scope changes.

Accepted decisions are recorded as ADRs:

- [Auth0 through OIDC](docs/architecture/decisions/0001-auth0-oidc.md)
- [Workspace roles](docs/architecture/decisions/0002-workspace-roles.md)
- [Local storage adapter](docs/architecture/decisions/0003-local-storage-adapter.md)

## Prerequisites

- [uv](https://docs.astral.sh/uv/)
- Python 3.12, installed directly or managed by uv
- Tesseract OCR with the English language data
- Docker Desktop or another Compose-compatible container runtime for local
  PostgreSQL and Qdrant

## Create the dedicated environment

Run all commands from this `2.0` directory:

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

- Callback URL: `http://localhost:8502/oauth2callback`
- Logout URL: `http://localhost:8502`
- Web origin: `http://localhost:8502`

Set `AUTH0_ISSUER` and `AUTH0_AUDIENCE` in ignored `.env`. Then create the
ignored Streamlit secrets file:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Replace every placeholder in that file. `AUTH0_ISSUER` must match the access
token `iss` claim exactly, including its trailing slash. The frontend requests
the configured audience so Auth0 returns an API access token rather than an
opaque user-session token.

## Start PostgreSQL and Qdrant

After configuring `.env` and installing a container runtime:

```bash
docker compose up -d
docker compose ps
```

Local endpoints are intentionally separated from V1:

| Component | Endpoint |
| --- | --- |
| Streamlit | `http://127.0.0.1:8502` |
| FastAPI backend | `http://127.0.0.1:8000` |
| PostgreSQL | `127.0.0.1:5433` |
| Qdrant HTTP | `http://127.0.0.1:6335` |
| Qdrant gRPC | `127.0.0.1:6336` |

PostgreSQL and Qdrant use Compose-managed Phase 2 volumes. Do not mount or
reuse V1 runtime data.

Readiness checks:

```bash
docker compose exec postgres pg_isready -U mm_rag -d mm_rag_phase2
curl --fail http://127.0.0.1:6335/readyz
```

Stop services without deleting their volumes:

```bash
docker compose down
```

Do not add `-v` unless you explicitly intend to delete the Phase 2 PostgreSQL
and Qdrant data volumes.

## Apply database migrations

The migration history contains the infrastructure baseline and the Phase 2.1
identity/workspace schema:

```bash
uv run alembic upgrade head
uv run alembic current
```

All future PostgreSQL schema changes must be created and reviewed as Alembic
revisions. Runtime code and migrations share `backend.app.db.base.Base.metadata`.

## Run and verify the FastAPI backend

Start the backend on its loopback-only development endpoint:

```bash
uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

API documentation is available at `http://127.0.0.1:8000/docs`.

| Endpoint | Meaning | Response behavior |
| --- | --- | --- |
| `GET /api/v1/health/live` | The API process can respond | HTTP 200 without checking external services |
| `GET /api/v1/health/ready` | PostgreSQL and Qdrant are usable | HTTP 200 when ready; safe HTTP 503 otherwise |
| `GET /api/v1/users/me` | Provision/read the authenticated user and personal workspace | HTTP 200 with valid Auth0 token; 401 otherwise |
| `GET /api/v1/workspaces` | List only the caller's workspaces | HTTP 200 with membership-scoped results |
| `POST /api/v1/workspaces` | Create a workspace owned by the caller | HTTP 201 with an `owner` membership |
| `GET /api/v1/workspaces/{id}` | Read one authorized workspace | HTTP 404 for missing or unauthorized workspace |

Verify from another terminal:

```bash
curl --fail http://127.0.0.1:8000/api/v1/health/live
curl --fail http://127.0.0.1:8000/api/v1/health/ready
```

Readiness responses contain only component state and latency. They never expose
connection strings, passwords, API keys, stack traces, or raw dependency errors.

## Run the current Streamlit baseline

```bash
uv run streamlit run ui/app.py
```

The committed `.streamlit/config.toml` assigns Phase 2 port `8502` and disables
usage-statistics collection.

## Run the authenticated Phase 2 shell

After completing the Auth0 configuration and starting FastAPI:

```bash
uv run streamlit run frontend/streamlit_app.py
```

The shell uses native Streamlit OIDC login, keeps the access token out of Session
State, calls the protected current-user API, and displays only authorized
workspaces. The existing `ui/app.py` remains available as the preserved RAG flow
until its capabilities are moved behind FastAPI.

## Verify the environment

```bash
uv lock --check
uv sync --locked
uv run pytest
uv run ruff check backend frontend migrations tests
uv run mypy backend frontend tests/backend
```

The tests verify Python 3.12, the Phase 2 interpreter path, required imports,
Streamlit startup, configuration, transactions, migrations, liveness,
readiness-success behavior, and safe dependency-failure behavior.

With PostgreSQL and Qdrant running, include the live integration check:

```bash
MM_RAG_RUN_INTEGRATION_TESTS=1 uv run pytest tests/backend/test_integration_services.py
```

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
├── compose.yaml              # Phase 2 PostgreSQL and Qdrant
├── docs/                     # Living project plan, architecture, and ADRs
├── frontend/                 # Authenticated Phase 2 Streamlit shell
├── migrations/               # Versioned PostgreSQL schema changes
├── pyproject.toml            # Dependencies and Python tool configuration
├── uv.lock                   # Exact reproducible dependency resolution
├── src/                      # Current RAG implementation
├── ui/app.py                 # Current Streamlit baseline
└── tests/                    # Unit, integration, environment, and smoke tests
```

Future milestones will add documents, collections, tenant-safe Qdrant filters,
persistent backend-mediated RAG chat, additional frontend pages, reusable
RAG-core packages, and CI while preserving verified baseline behavior.
