from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_ROOT = PROJECT_ROOT / "deploy" / "oci"
REQUIRED_FILES = (
    PROJECT_ROOT / "Dockerfile",
    DEPLOY_ROOT / "Caddyfile",
    DEPLOY_ROOT / "compose.yaml",
    DEPLOY_ROOT / "runtime.env.example",
    DEPLOY_ROOT / "streamlit-secrets.toml.example",
    DEPLOY_ROOT / "terraform" / "main.tf",
    DEPLOY_ROOT / "terraform" / ".terraform.lock.hcl",
    PROJECT_ROOT / "frontend-next" / "package-lock.json",
    PROJECT_ROOT / "frontend-next" / "Dockerfile",
)
LOCKFILE = PROJECT_ROOT / "uv.lock"
SENSITIVE_KEYS = {
    "OPENAI_API_KEY",
    "GRAFANA_ADMIN_PASSWORD",
    "POSTGRES_PASSWORD",
    "RABBITMQ_PASSWORD",
    "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY",
    "AUTH0_CLIENT_SECRET",
    "AUTH0_SECRET",
}
IMAGE_KEYS = {
    "CADDY_IMAGE",
    "LGTM_IMAGE",
    "MM_RAG_IMAGE",
    "NEXT_CANDIDATE_IMAGE",
    "OTEL_COLLECTOR_IMAGE",
    "POSTGRES_IMAGE",
    "QDRANT_IMAGE",
    "RABBITMQ_IMAGE",
    "SEAWEEDFS_IMAGE",
}


def validate_phase8_deployment() -> dict[str, object]:
    for path in REQUIRED_FILES:
        if not path.is_file():
            raise ValueError(f"Missing deployment contract file: {path.relative_to(PROJECT_ROOT)}")

    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    lockfile = LOCKFILE.read_text(encoding="utf-8")
    compose = (DEPLOY_ROOT / "compose.yaml").read_text(encoding="utf-8")
    caddy = (DEPLOY_ROOT / "Caddyfile").read_text(encoding="utf-8")
    environment = _parse_example_environment(DEPLOY_ROOT / "runtime.env.example")

    if "COPY frontend ./frontend" not in dockerfile:
        raise ValueError("Runtime image must contain the Streamlit frontend")
    if "USER mmrag" not in dockerfile:
        raise ValueError("Runtime image must use the unprivileged application user")
    if 'name = "nvidia-cuda-' in lockfile or 'name = "nvidia-cudnn-' in lockfile:
        raise ValueError("OCI CPU image dependency lock must not contain NVIDIA CUDA packages")
    if "APP_ENV: staging" not in compose:
        raise ValueError("Learning deployment must not claim the production environment")
    if "  models:" not in compose or "service_completed_successfully" not in compose:
        raise ValueError("Application startup must wait for one-shot model provisioning")
    if _services_with_published_ports(compose) != {"edge"}:
        raise ValueError("Only the HTTPS edge service may publish host ports")
    if "admin off" not in caddy or "reverse_proxy api:8003" not in caddy:
        raise ValueError("Caddy must disable its admin endpoint and proxy the API privately")
    if 'profiles: ["nextjs-candidate"]' not in compose:
        raise ValueError("Next.js must remain an opt-in candidate profile")
    if "MM_RAG_UI_UPSTREAM=ui:8503" not in (DEPLOY_ROOT / "runtime.env.example").read_text(
        encoding="utf-8"
    ):
        raise ValueError("Streamlit must remain the default Phase 8 frontend")

    missing_images = sorted(IMAGE_KEYS - environment.keys())
    if missing_images:
        raise ValueError(f"Missing image references: {', '.join(missing_images)}")
    for key in IMAGE_KEYS:
        value = environment[key]
        if "@sha256:" not in value or "REPLACE_WITH_64_HEX_DIGEST" not in value:
            raise ValueError(f"{key} must demonstrate digest pinning without using a real digest")
    populated_secrets = sorted(key for key in SENSITIVE_KEYS if environment.get(key))
    if populated_secrets:
        raise ValueError(f"Example environment contains populated secrets: {', '.join(populated_secrets)}")

    result: dict[str, object] = {
        "image_contracts": len(IMAGE_KEYS),
        "public_tcp_ports": [80, 443],
        "schema_revision": "phase8-oci-deployment-contract-v2",
        "status": "valid",
    }
    return result


def _parse_example_environment(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key:
            raise ValueError(f"Invalid example environment line: {raw_line}")
        values[key] = value
    return values


def _services_with_published_ports(compose: str) -> set[str]:
    services: set[str] = set()
    current_service: str | None = None
    in_services = False
    for line in compose.splitlines():
        if line == "services:":
            in_services = True
            continue
        if in_services and line and not line.startswith(" "):
            break
        if not in_services:
            continue
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            current_service = line.strip()[:-1]
        elif line == "    ports:" and current_service is not None:
            services.add(current_service)
    return services


def main() -> None:
    print(json.dumps(validate_phase8_deployment(), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
