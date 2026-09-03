from uuid import uuid4

import pytest

from backend.app.models.visual import ContentRegionKind
from backend.app.visual.provenance import (
    ArtifactIdentity,
    NormalizedBoundingBox,
    RegionLocator,
    content_sha256,
    extractor_config_sha256,
)


def _locator() -> RegionLocator:
    return RegionLocator(
        page_number=2,
        page_render_sha256="a" * 64,
        kind=ContentRegionKind.CHART,
        bbox=NormalizedBoundingBox(0.1, 0.2, 0.3, 0.4),
        page_width=612.0,
        page_height=792.0,
        rotation=0,
        extractor_name="fixture",
        extractor_revision="1.0.0",
        extractor_config_sha256=extractor_config_sha256({"dpi": 144}),
        ordinal=3,
    )


def test_region_identity_is_stable_and_generation_scoped() -> None:
    generation_id = uuid4()
    first = _locator()
    second = _locator()

    assert first.sha256 == second.sha256
    assert first.stable_id(generation_id) == second.stable_id(generation_id)
    assert first.stable_id(generation_id) != second.stable_id(uuid4())


def test_region_identity_changes_when_source_geometry_changes() -> None:
    first = _locator()
    changed = RegionLocator(
        page_number=first.page_number,
        page_render_sha256=first.page_render_sha256,
        kind=first.kind,
        bbox=NormalizedBoundingBox(0.1, 0.2, 0.31, 0.4),
        page_width=first.page_width,
        page_height=first.page_height,
        rotation=first.rotation,
        extractor_name=first.extractor_name,
        extractor_revision=first.extractor_revision,
        extractor_config_sha256=first.extractor_config_sha256,
        ordinal=first.ordinal,
    )

    assert first.sha256 != changed.sha256


def test_artifact_identity_binds_content_and_producer() -> None:
    generation_id = uuid4()
    region_id = _locator().stable_id(generation_id)
    source = ArtifactIdentity(
        region_id=region_id,
        kind="region_crop",
        content_sha256=content_sha256(b"crop"),
        producer_name="fixture",
        producer_revision="1.0.0",
    )
    changed = ArtifactIdentity(
        region_id=region_id,
        kind="region_crop",
        content_sha256=content_sha256(b"changed"),
        producer_name="fixture",
        producer_revision="1.0.0",
    )

    assert source.stable_id(generation_id) == source.stable_id(generation_id)
    assert source.stable_id(generation_id) != changed.stable_id(generation_id)


@pytest.mark.parametrize(
    "bbox",
    [
        (-0.1, 0.0, 0.2, 0.2),
        (0.0, 0.0, 0.0, 0.2),
        (0.9, 0.0, 0.2, 0.2),
        (0.0, 0.9, 0.2, 0.2),
    ],
)
def test_invalid_region_geometry_is_rejected(bbox: tuple[float, float, float, float]) -> None:
    with pytest.raises(ValueError):
        NormalizedBoundingBox(*bbox)
