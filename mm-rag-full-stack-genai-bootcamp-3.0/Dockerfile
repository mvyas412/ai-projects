FROM ghcr.io/astral-sh/uv:0.8.13-python3.12-bookworm-slim

ARG BUILD_REVISION=uncommitted
ARG BUILD_CREATED=unknown
ARG PREFETCH_PHASE5_MODELS=1

LABEL org.opencontainers.image.title="MM-RAG" \
    org.opencontainers.image.description="Tenant-safe multimodal RAG application runtime" \
    org.opencontainers.image.revision="${BUILD_REVISION}" \
    org.opencontainers.image.created="${BUILD_CREATED}" \
    org.opencontainers.image.source="https://github.com/mvyas412/ai-projects"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update \
    && apt-get upgrade --yes \
    && apt-get install --yes --no-install-recommends curl tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY README.md alembic.ini ./
COPY backend ./backend
COPY evaluation ./evaluation
COPY frontend ./frontend
COPY migrations ./migrations
COPY observability ./observability
COPY scripts ./scripts
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev
RUN if [ "${PREFETCH_PHASE5_MODELS}" = "1" ]; then \
        uv run --no-sync python -m scripts.prefetch_phase5_models; \
    fi

RUN useradd --create-home --uid 10001 mmrag \
    && mkdir -p /app/data/runtime/docling-models /app/data/runtime/health /app/data/runtime/models \
    && chown -R mmrag:mmrag /app/data /home/mmrag
USER mmrag

CMD ["uv", "run", "python", "-m", "backend.app.workers.ingestion_worker"]
