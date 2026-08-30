.PHONY: setup services services-stop migrate api ui check check-live check-acceptance

setup:
	uv python install 3.12
	uv sync --locked

services:
	docker compose up -d
	docker compose ps

services-stop:
	docker compose down

migrate:
	uv run alembic upgrade head
	uv run alembic current

api:
	uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

ui:
	uv run streamlit run frontend/streamlit_app.py

check:
	./scripts/verify_phase2.sh

check-live:
	MM_RAG_RUN_INTEGRATION_TESTS=1 ./scripts/verify_phase2.sh --live

check-acceptance: check-live
	uv run python -m scripts.run_openai_acceptance
