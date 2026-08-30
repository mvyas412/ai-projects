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
- Automated environment and Streamlit startup smoke tests.

Authentication, product tables, workspaces, and the new frontend structure will
be introduced incrementally after this backend foundation.

## Architecture and roadmap

The living [architecture handbook](docs/architecture/ARCHITECTURE.md) contains:

- The whole-system target architecture and end-to-end data flows.
- A focused component and interaction diagram for every phase from 1 through 9.
- Current implementation status, architecture invariants, open technology
  decisions, and documentation-maintenance rules.

Planned components are explicitly labeled so the diagrams do not imply that
future capabilities have already been implemented.

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

The backend will own OpenAI, PostgreSQL, and Qdrant credentials. The Streamlit
frontend should receive only its API URL and, later, its own OIDC settings.

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

The initial migration establishes Alembic's versioned baseline without creating
product tables prematurely:

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

## Verify the environment

```bash
uv lock --check
uv sync --locked
uv run pytest
uv run ruff check backend migrations tests
uv run mypy backend tests/backend
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
├── .streamlit/config.toml    # Shareable Streamlit settings
├── alembic.ini               # Migration runner configuration
├── backend/app/              # FastAPI, settings, database, schemas, and services
├── compose.yaml              # Phase 2 PostgreSQL and Qdrant
├── docs/architecture/        # Living whole-system and Phase 1–9 diagrams
├── migrations/               # Versioned PostgreSQL schema changes
├── pyproject.toml            # Dependencies and Python tool configuration
├── uv.lock                   # Exact reproducible dependency resolution
├── src/                      # Current RAG implementation
├── ui/app.py                 # Current Streamlit baseline
└── tests/                    # Unit, integration, environment, and smoke tests
```

Future milestones will introduce product models, authentication, tenant-safe
workspaces, a multipage `frontend/`, reusable RAG-core packages, and CI while
preserving the verified baseline behavior.
