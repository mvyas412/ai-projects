from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "mm-rag-phase8-release-v1"
REQUIRED_IMAGES = {
    "app",
    "caddy",
    "postgres",
    "qdrant",
    "rabbitmq",
    "seaweedfs",
}
DIGEST_IMAGE = re.compile(r"^[^\s:@]+(?:/[^\s:@]+)*(?::[^\s@]+)?@sha256:[0-9a-f]{64}$")


def validate_release_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA:
        raise ValueError("Unsupported release manifest schema")
    revision = payload.get("git_revision")
    migration = payload.get("migration_revision")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("git_revision must be a full Git commit SHA")
    if not isinstance(migration, str) or not re.fullmatch(r"[0-9A-Za-z_-]+", migration):
        raise ValueError("migration_revision is missing or malformed")

    images = payload.get("images")
    if not isinstance(images, dict):
        raise ValueError("images must be an object")
    missing = sorted(REQUIRED_IMAGES - images.keys())
    if missing:
        raise ValueError(f"Release manifest is missing images: {', '.join(missing)}")
    invalid = sorted(name for name, image in images.items() if not _digest_image(image))
    if invalid:
        raise ValueError(f"Release images are not digest-pinned: {', '.join(invalid)}")

    initial_release = payload.get("initial_release", False)
    if not isinstance(initial_release, bool):
        raise ValueError("initial_release must be a boolean")
    rollback = payload.get("rollback_manifest")
    if initial_release:
        if rollback is not None:
            raise ValueError("An initial release cannot name a rollback_manifest")
    elif not isinstance(rollback, str) or not rollback.endswith(".json"):
        raise ValueError("A previous digest-pinned rollback_manifest is required")
    forbidden = {"secret", "password", "token", "private_key"}
    exposed = sorted(forbidden & _all_keys(payload))
    if exposed:
        raise ValueError(f"Release manifest contains forbidden fields: {', '.join(exposed)}")
    return {
        "images": len(images),
        "initial_release": initial_release,
        "migration_revision": migration,
        "schema": SCHEMA,
        "status": "valid",
    }


def _digest_image(value: object) -> bool:
    return isinstance(value, str) and DIGEST_IMAGE.fullmatch(value) is not None


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        mapping_keys = {str(key).lower() for key in value}
        for nested in value.values():
            mapping_keys.update(_all_keys(nested))
        return mapping_keys
    if isinstance(value, list):
        list_keys: set[str] = set()
        for nested in value:
            list_keys.update(_all_keys(nested))
        return list_keys
    return set()


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate an immutable Phase 8 release manifest")
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate_release_manifest(args.manifest), sort_keys=True))


if __name__ == "__main__":
    main()
