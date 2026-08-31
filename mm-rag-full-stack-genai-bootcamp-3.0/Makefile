.PHONY: setup services runtime runtime-stop services-stop migrate api ui dispatcher worker operations-status operations-retention-preview backup check check-live check-acceptance

setup:
	uv python install 3.12
	uv sync --locked

services:
	docker compose up -d
	docker compose ps

runtime:
	docker compose --profile runtime up -d dispatcher worker
	docker compose --profile runtime ps

runtime-stop:
	docker compose --profile runtime stop dispatcher worker

services-stop:
	docker compose down

migrate:
	uv run alembic upgrade head
	uv run alembic current

api:
	uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8003

ui:
	uv run streamlit run frontend/streamlit_app.py

dispatcher:
	uv run python -m backend.app.workers.outbox_dispatcher

worker:
	uv run python -m backend.app.workers.ingestion_worker

operations-status:
	uv run python -m backend.app.workers.operations status

operations-retention-preview:
	uv run python -m backend.app.workers.operations retention-preview

backup:
	./scripts/backup_phase3_postgres.sh

check:
	./scripts/verify_phase3.sh

check-live:
	MM_RAG_RUN_INTEGRATION_TESTS=1 MM_RAG_RUN_S3_INTEGRATION_TESTS=1 MM_RAG_RUN_RABBITMQ_INTEGRATION_TESTS=1 ./scripts/verify_phase3.sh --live

check-acceptance: check-live
	uv run python -m scripts.run_openai_acceptance
