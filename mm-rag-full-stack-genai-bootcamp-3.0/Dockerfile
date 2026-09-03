FROM ghcr.io/astral-sh/uv:0.8.13-python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY alembic.ini ./
COPY backend ./backend
COPY migrations ./migrations
COPY scripts ./scripts
RUN uv sync --locked --no-dev
RUN uv run --no-sync python -m scripts.prefetch_phase5_models

RUN useradd --create-home --uid 10001 mmrag \
    && mkdir -p /app/data/runtime/health \
    && chown -R mmrag:mmrag /app
USER mmrag

CMD ["uv", "run", "python", "-m", "backend.app.workers.ingestion_worker"]
