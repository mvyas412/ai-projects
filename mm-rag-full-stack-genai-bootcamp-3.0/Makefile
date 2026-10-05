.PHONY: setup models models-verify phase6-models phase6-models-verify services observability observability-stop observability-status observability-baseline observability-baseline-status runtime runtime-stop services-stop migrate api ui dispatcher worker operations-status operations-retention-preview backup google-drive-authorize google-drive-probe google-drive-propagation phase5-evaluation phase6-evaluation phase7-evaluation phase8-deployment-validate phase8-next-check phase10-policy-check phase10-operations-check phase10-backup phase10-restore-drill phase10-release-plan phase10-capacity phase10-retention-preview phase10-evidence-gate phase11-policy-check phase11-rehearsal phase11-evidence-gate phase11-canary-readiness phase11-technical-template phase11-technical-gate check check-live check-acceptance

setup:
	uv python install 3.12
	uv sync --locked
	$(MAKE) models

models:
	uv run python -m scripts.prefetch_phase5_models

models-verify:
	uv run python -m scripts.prefetch_phase5_models --verify-only

phase6-models:
	uv run python -m scripts.prefetch_phase6_models

phase6-models-verify:
	uv run python -m scripts.prefetch_phase6_models --verify-only

services:
	docker compose up -d
	docker compose ps

observability:
	docker compose --profile observability up -d lgtm otel-collector
	docker compose --profile observability ps lgtm otel-collector

observability-stop:
	docker compose --profile observability stop otel-collector lgtm

observability-status:
	uv run python -m scripts.phase7_observability status

observability-baseline:
	uv run python -m scripts.phase7_observability record-baseline

observability-baseline-status:
	uv run python -m scripts.phase7_observability baseline-status

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

google-drive-authorize:
	@test -n "$(GOOGLE_DRIVE_CLIENT_CONFIG)" || (echo "Set GOOGLE_DRIVE_CLIENT_CONFIG to the private Desktop OAuth client JSON path" && exit 2)
	uv run python -m scripts.google_drive_oauth --client-config "$(GOOGLE_DRIVE_CLIENT_CONFIG)"

google-drive-probe:
	@test -n "$(GOOGLE_DRIVE_CLIENT_CONFIG)" || (echo "Set GOOGLE_DRIVE_CLIENT_CONFIG to the private Desktop OAuth client JSON path" && exit 2)
	uv run python -m scripts.google_drive_probe --client-config "$(GOOGLE_DRIVE_CLIENT_CONFIG)"

google-drive-propagation:
	@test -n "$(GOOGLE_DRIVE_CLIENT_CONFIG)" || (echo "Set GOOGLE_DRIVE_CLIENT_CONFIG to the private Desktop OAuth client JSON path" && exit 2)
	@test -n "$(GOOGLE_DRIVE_PROPAGATION_STAGE)" || (echo "Set GOOGLE_DRIVE_PROPAGATION_STAGE to baseline, expanded, restored, or deleted" && exit 2)
	uv run python -m scripts.google_drive_propagation_probe "$(GOOGLE_DRIVE_PROPAGATION_STAGE)" --client-config "$(GOOGLE_DRIVE_CLIENT_CONFIG)" $(if $(GOOGLE_DRIVE_FIXTURE_NAME),--fixture-name "$(GOOGLE_DRIVE_FIXTURE_NAME)")

phase5-evaluation:
	uv run python -m scripts.build_phase5_v4_fixture --check
	uv run python -m scripts.run_phase5_evaluation

phase6-evaluation:
	uv run python -m scripts.build_phase6_v1_fixture --check
	uv run python -m scripts.run_phase6_evaluation --check
	uv run python -m scripts.run_phase6_candidate --check

phase7-evaluation:
	uv run python -m scripts.run_phase7_evaluation --check

phase8-deployment-validate:
	uv run python -m scripts.validate_phase8_deployment
	uv run python -m scripts.phase8_release deploy/oci/release-manifest.example.json

phase8-next-check:
	cd frontend-next && npm ci && npm audit && npm test && npm run typecheck && npm run build

phase10-policy-check:
	uv run python -m scripts.phase10_operations policy operations/phase10-policy.json

phase10-operations-check: phase10-policy-check
	uv run pytest -q tests/test_phase10_*.py

phase10-backup:
	@test -n "$(WORK_DIRECTORY)" || (echo "Set WORK_DIRECTORY to a private mode-0700 path" && exit 2)
	@test -n "$(OUTPUT_DIRECTORY)" || (echo "Set OUTPUT_DIRECTORY to a private mode-0700 path" && exit 2)
	@test -n "$(RECIPIENT_FILE)" || (echo "Set RECIPIENT_FILE to the public age recipient path" && exit 2)
	uv run python -m scripts.phase10_backup_cycle --work-directory "$(WORK_DIRECTORY)" --output-directory "$(OUTPUT_DIRECTORY)" --recipient-file "$(RECIPIENT_FILE)" $(if $(UPLOAD),--upload)

phase10-restore-drill:
	@test -n "$(BUNDLE)" || (echo "Set BUNDLE to an encrypted backup path" && exit 2)
	@test -n "$(IDENTITY_FILE)" || (echo "Set IDENTITY_FILE to the private age identity path" && exit 2)
	@test -n "$(WORK_DIRECTORY)" || (echo "Set WORK_DIRECTORY to a disposable private path" && exit 2)
	uv run python -m scripts.phase10_restore_drill "$(BUNDLE)" --identity-file "$(IDENTITY_FILE)" --work-directory "$(WORK_DIRECTORY)" --expected-migration 20260919_0019 --output evaluation/phase10/results/isolated-restore.json

phase10-release-plan:
	@test -n "$(INPUT)" || (echo "Set INPUT to an ignored release plan JSON path" && exit 2)
	uv run python -m scripts.phase10_release plan "$(INPUT)"

phase10-capacity:
	@test -n "$(INPUT)" || (echo "Set INPUT to an ignored capacity snapshot JSON path" && exit 2)
	uv run python -m scripts.phase10_operations capacity "$(INPUT)"

phase10-retention-preview:
	@test -n "$(INPUT)" || (echo "Set INPUT to an ignored preview JSON path" && exit 2)
	uv run python -m scripts.phase10_operations retention-preview "$(INPUT)"

phase10-evidence-gate:
	uv run python -m scripts.phase10_operations gate evaluation/phase10/results

phase11-policy-check:
	uv run python -m scripts.phase11_pilot policy

phase11-rehearsal: phase11-policy-check
	uv run python -m scripts.phase11_pilot rehearse --output evaluation/phase11/results/internal-rehearsal.json

phase11-evidence-gate:
	uv run python -m scripts.phase11_pilot gate evaluation/phase11/results/internal-rehearsal.json

phase11-canary-readiness:
	uv run python -m scripts.phase11_pilot canary-readiness

phase11-technical-template: phase11-policy-check
	uv run python -m scripts.phase11_pilot technical-template --output evaluation/phase11/results/technical-rehearsal.json

phase11-technical-gate:
	uv run python -m scripts.phase11_pilot technical-gate evaluation/phase11/results/technical-rehearsal.json

check:
	./scripts/verify_phase3.sh

check-live:
	MM_RAG_RUN_INTEGRATION_TESTS=1 MM_RAG_RUN_S3_INTEGRATION_TESTS=1 MM_RAG_RUN_RABBITMQ_INTEGRATION_TESTS=1 ./scripts/verify_phase3.sh --live

check-acceptance: check-live models-verify phase5-evaluation
	@test -n "$(PHASE5_EMBEDDING_COST_USD_PER_MILLION_TOKENS)" || (echo "Set PHASE5_EMBEDDING_COST_USD_PER_MILLION_TOKENS before the approved paid run" && exit 2)
	uv run python -m scripts.run_phase5_benchmark --allow-paid-openai --embedding-cost-per-million-tokens "$(PHASE5_EMBEDDING_COST_USD_PER_MILLION_TOKENS)"
	RAG_RETRIEVAL_PROFILE=hybrid-v3 uv run python -m scripts.run_openai_acceptance
