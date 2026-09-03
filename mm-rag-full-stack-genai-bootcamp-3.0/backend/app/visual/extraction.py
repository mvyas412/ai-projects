from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import version
from io import BytesIO
from pathlib import Path
from typing import Protocol

from PIL import Image

from backend.app.models.visual import ContentRegionKind
from backend.app.visual.artifacts import (
    VisualModelArtifactError,
    verify_docling_artifacts,
)
from backend.app.visual.provenance import NormalizedBoundingBox, content_sha256


class VisualExtractionError(RuntimeError):
    """A non-disclosing local extraction failure."""


@dataclass(frozen=True, slots=True)
class ExtractedTable:
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class ExtractedRegion:
    page_number: int
    kind: ContentRegionKind
    ordinal: int
    bbox: NormalizedBoundingBox
    page_width: float
    page_height: float
    rotation: int
    page_render: bytes
    crop: bytes
    source_caption: str | None
    ocr_text: str | None
    confidence: float | None
    table: ExtractedTable | None = None

    @property
    def page_render_sha256(self) -> str:
        return content_sha256(self.page_render)


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    extractor_name: str
    extractor_revision: str
    regions: tuple[ExtractedRegion, ...]


class DocumentStructureExtractor(Protocol):
    def extract(self, content: bytes, media_type: str) -> ExtractionResult: ...


class DoclingStructureExtractor:
    """Run the pinned local structural profile with all remote services disabled."""

    def __init__(
        self,
        artifacts_path: Path,
        *,
        image_scale: float = 2.0,
        timeout_seconds: int = 300,
        max_pages: int = 250,
    ) -> None:
        self._artifacts_path = artifacts_path
        self._image_scale = image_scale
        self._timeout_seconds = timeout_seconds
        self._max_pages = max_pages

    def extract(self, content: bytes, media_type: str) -> ExtractionResult:
        if media_type.startswith("image/"):
            return _extract_standalone_image(content)
        if media_type != "application/pdf":
            raise VisualExtractionError("The structural extractor does not support this format")
        try:
            verify_docling_artifacts(self._artifacts_path)
        except VisualModelArtifactError:
            raise VisualExtractionError("Pinned visual extraction artifacts are unavailable")
        try:
            document = self._convert(content)
            regions = self._regions(document)
        except VisualExtractionError:
            raise
        except Exception as exc:
            raise VisualExtractionError("Local visual extraction failed") from exc
        return ExtractionResult(
            extractor_name="docling",
            extractor_revision=version("docling"),
            regions=tuple(regions),
        )

    def _convert(self, content: bytes):
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.document import DocumentStream
        from docling.datamodel.pipeline_options import (
            PdfPipelineOptions,
            TableFormerMode,
            TableStructureOptions,
            TesseractCliOcrOptions,
        )
        from docling.document_converter import DocumentConverter, PdfFormatOption

        options = PdfPipelineOptions(
            artifacts_path=self._artifacts_path,
            document_timeout=float(self._timeout_seconds),
            enable_remote_services=False,
            allow_external_plugins=False,
            do_ocr=True,
            ocr_options=TesseractCliOcrOptions(lang=["eng"]),
            do_table_structure=True,
            table_structure_options=TableStructureOptions(
                do_cell_matching=True, mode=TableFormerMode.ACCURATE
            ),
            do_picture_description=False,
            do_picture_classification=False,
            images_scale=self._image_scale,
            generate_page_images=True,
            generate_picture_images=True,
            generate_table_images=True,
        )
        converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
        )
        stream = DocumentStream(name="document.pdf", stream=BytesIO(content))
        return converter.convert(stream, max_num_pages=self._max_pages).document

    @staticmethod
    def _regions(document) -> list[ExtractedRegion]:
        from docling_core.types.doc import TableItem

        candidates = [*document.pictures, *document.tables]
        ordered = sorted(
            candidates,
            key=lambda item: (
                item.prov[0].page_no if item.prov else 0,
                item.prov[0].bbox.t if item.prov else 0.0,
                item.prov[0].bbox.l if item.prov else 0.0,
                item.self_ref,
            ),
        )
        regions: list[ExtractedRegion] = []
        for ordinal, item in enumerate(ordered):
            if not item.prov:
                continue
            provenance = item.prov[0]
            page = document.pages.get(provenance.page_no)
            if page is None or page.image is None or page.image.pil_image is None:
                raise VisualExtractionError("A required page render is unavailable")
            page_image = page.image.pil_image.convert("RGB")
            page_render = _png_bytes(page_image)
            bbox = provenance.bbox.to_top_left_origin(page.size.height).normalized(page.size)
            x = min(0.999999, _clamp(bbox.l))
            y = min(0.999999, _clamp(bbox.t))
            normalized = NormalizedBoundingBox(
                x,
                y,
                min(1.0 - x, _clamp(bbox.width, positive=True)),
                min(1.0 - y, _clamp(bbox.height, positive=True)),
            )
            crop_image = item.get_image(document)
            if crop_image is None:
                crop_image = _crop(page_image, normalized)
            caption = item.caption_text(document).strip() or None
            table = _table_data(item, document) if isinstance(item, TableItem) else None
            kind = (
                ContentRegionKind.TABLE
                if isinstance(item, TableItem)
                else _picture_kind(caption)
            )
            ocr_text = _table_text(table) if table is not None else caption
            regions.append(
                ExtractedRegion(
                    page_number=provenance.page_no,
                    kind=kind,
                    ordinal=ordinal,
                    bbox=normalized,
                    page_width=page.size.width,
                    page_height=page.size.height,
                    rotation=0,
                    page_render=page_render,
                    crop=_png_bytes(crop_image.convert("RGB")),
                    source_caption=caption,
                    ocr_text=ocr_text,
                    confidence=None,
                    table=table,
                )
            )
        return regions


def _table_data(item, document) -> ExtractedTable:
    frame = item.export_to_dataframe(document)
    columns = tuple(str(value).strip() for value in frame.columns)
    rows = tuple(
        tuple("" if value is None else str(value).strip() for value in row)
        for row in frame.itertuples(index=False, name=None)
    )
    return ExtractedTable(columns=columns, rows=rows)


def _extract_standalone_image(content: bytes) -> ExtractionResult:
    try:
        with Image.open(BytesIO(content)) as source:
            image = source.convert("RGB")
    except Exception as exc:
        raise VisualExtractionError("Local image extraction failed") from exc
    rendered = _png_bytes(image)
    return ExtractionResult(
        extractor_name="pillow",
        extractor_revision=version("pillow"),
        regions=(
            ExtractedRegion(
                page_number=1,
                kind=ContentRegionKind.PHOTO,
                ordinal=0,
                bbox=NormalizedBoundingBox(0.0, 0.0, 1.0, 1.0),
                page_width=float(image.width),
                page_height=float(image.height),
                rotation=0,
                page_render=rendered,
                crop=rendered,
                source_caption=None,
                ocr_text=None,
                confidence=1.0,
            ),
        ),
    )


def _table_text(table: ExtractedTable) -> str:
    lines = [" | ".join(table.columns)] if table.columns else []
    lines.extend(" | ".join(row) for row in table.rows)
    return "\n".join(lines)


def _picture_kind(caption: str | None) -> ContentRegionKind:
    text = (caption or "").casefold()
    if any(token in text for token in ("chart", "graph", "plot")):
        return ContentRegionKind.CHART
    if any(token in text for token in ("diagram", "flow", "architecture")):
        return ContentRegionKind.DIAGRAM
    if any(token in text for token in ("photo", "photograph")):
        return ContentRegionKind.PHOTO
    return ContentRegionKind.FIGURE


def _png_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", optimize=False)
    return output.getvalue()


def _crop(image: Image.Image, bbox: NormalizedBoundingBox) -> Image.Image:
    left = round(bbox.x * image.width)
    top = round(bbox.y * image.height)
    right = round((bbox.x + bbox.width) * image.width)
    bottom = round((bbox.y + bbox.height) * image.height)
    return image.crop((left, top, max(left + 1, right), max(top + 1, bottom)))


def _clamp(value: float, *, positive: bool = False) -> float:
    lower = 0.000001 if positive else 0.0
    return min(1.0, max(lower, float(value)))
