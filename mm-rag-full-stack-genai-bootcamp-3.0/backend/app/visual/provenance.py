from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID, uuid5

from backend.app.models.visual import ContentRegionKind

REGION_NAMESPACE = UUID("b77a6207-31b2-48a7-8ae1-cf9bea9ac193")
ARTIFACT_NAMESPACE = UUID("84704a80-2097-473c-86e0-e1b69b13c637")
LOCATOR_SCHEMA_REVISION = "region-locator-v1"
ARTIFACT_SCHEMA_REVISION = "content-artifact-v1"


@dataclass(frozen=True, slots=True)
class NormalizedBoundingBox:
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Bounding-box values must be finite")
        if self.x < 0 or self.y < 0 or self.width <= 0 or self.height <= 0:
            raise ValueError("Bounding box must have a positive normalized area")
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("Bounding box must remain within the page")

    def canonical(self) -> tuple[str, str, str, str]:
        return (
            f"{self.x:.6f}",
            f"{self.y:.6f}",
            f"{self.width:.6f}",
            f"{self.height:.6f}",
        )


@dataclass(frozen=True, slots=True)
class RegionLocator:
    page_number: int
    page_render_sha256: str
    kind: ContentRegionKind
    bbox: NormalizedBoundingBox
    page_width: float
    page_height: float
    rotation: int
    extractor_name: str
    extractor_revision: str
    extractor_config_sha256: str
    ordinal: int

    def __post_init__(self) -> None:
        if self.page_number <= 0:
            raise ValueError("Page number must be positive")
        if self.ordinal < 0:
            raise ValueError("Region ordinal must not be negative")
        if self.page_width <= 0 or self.page_height <= 0:
            raise ValueError("Page geometry must be positive")
        if self.rotation not in {0, 90, 180, 270}:
            raise ValueError("Page rotation is invalid")
        _require_sha256(self.page_render_sha256, "page render")
        _require_sha256(self.extractor_config_sha256, "extractor configuration")
        if not self.extractor_name.strip() or not self.extractor_revision.strip():
            raise ValueError("Extractor identity is required")

    def canonical_payload(self) -> dict[str, object]:
        x, y, width, height = self.bbox.canonical()
        return {
            "bbox": {"height": height, "width": width, "x": x, "y": y},
            "extractor": {
                "config_sha256": self.extractor_config_sha256,
                "name": self.extractor_name,
                "revision": self.extractor_revision,
            },
            "kind": self.kind.value,
            "locator_schema_revision": LOCATOR_SCHEMA_REVISION,
            "ordinal": self.ordinal,
            "page": {
                "height": f"{self.page_height:.6f}",
                "number": self.page_number,
                "render_sha256": self.page_render_sha256,
                "rotation": self.rotation,
                "width": f"{self.page_width:.6f}",
            },
        }

    @property
    def sha256(self) -> str:
        return _sha256_json(self.canonical_payload())

    def stable_id(self, generation_id: UUID) -> UUID:
        return uuid5(REGION_NAMESPACE, f"{generation_id}:{self.sha256}")


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    region_id: UUID
    kind: str
    content_sha256: str
    producer_name: str
    producer_revision: str
    schema_revision: str = ARTIFACT_SCHEMA_REVISION
    prompt_revision: str | None = None

    def __post_init__(self) -> None:
        _require_sha256(self.content_sha256, "artifact content")
        if not self.kind.strip() or not self.producer_name.strip():
            raise ValueError("Artifact kind and producer are required")
        if not self.producer_revision.strip() or not self.schema_revision.strip():
            raise ValueError("Artifact revision is required")

    def stable_id(self, generation_id: UUID) -> UUID:
        payload = {
            "content_sha256": self.content_sha256,
            "generation_id": str(generation_id),
            "kind": self.kind,
            "producer": {
                "name": self.producer_name,
                "revision": self.producer_revision,
            },
            "prompt_revision": self.prompt_revision,
            "region_id": str(self.region_id),
            "schema_revision": self.schema_revision,
        }
        return uuid5(ARTIFACT_NAMESPACE, _sha256_json(payload))


def extractor_config_sha256(config: dict[str, object]) -> str:
    return _sha256_json(config)


def content_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def canonical_manifest_sha256(payload: dict[str, object]) -> str:
    return _sha256_json(payload)


def _sha256_json(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{label.capitalize()} SHA-256 is invalid")
