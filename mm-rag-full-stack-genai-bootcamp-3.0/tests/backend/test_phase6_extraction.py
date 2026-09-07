from io import BytesIO

import pytest
from PIL import Image

from backend.app.models.visual import ContentRegionKind
from backend.app.visual.extraction import DoclingStructureExtractor, VisualExtractionError


def test_standalone_image_extraction_is_local_and_deterministic(tmp_path) -> None:
    source = BytesIO()
    Image.new("RGB", (32, 24), "teal").save(source, format="PNG")
    extractor = DoclingStructureExtractor(tmp_path / "models")

    first = extractor.extract(source.getvalue(), "image/png")
    second = extractor.extract(source.getvalue(), "image/png")

    assert first.extractor_name == "pillow"
    assert first.regions == second.regions
    assert first.regions[0].kind == ContentRegionKind.PHOTO
    assert first.regions[0].bbox.canonical() == (
        "0.000000",
        "0.000000",
        "1.000000",
        "1.000000",
    )


def test_pdf_extraction_fails_closed_when_pinned_artifacts_are_missing(tmp_path) -> None:
    extractor = DoclingStructureExtractor(tmp_path / "missing")

    with pytest.raises(VisualExtractionError, match="artifacts are unavailable"):
        extractor.extract(b"%PDF-1.7", "application/pdf")


def test_unsupported_format_fails_without_provider_fallback(tmp_path) -> None:
    extractor = DoclingStructureExtractor(tmp_path / "models")

    with pytest.raises(VisualExtractionError, match="does not support"):
        extractor.extract(b"content", "text/plain")
