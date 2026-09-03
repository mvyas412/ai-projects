from __future__ import annotations

import os
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from backend.app.models.visual import ContentRegionKind
from backend.app.visual.extraction import DoclingStructureExtractor

pytestmark = pytest.mark.integration


def _synthetic_visual_pdf() -> bytes:
    import pymupdf

    chart = Image.new("RGB", (320, 180), "white")
    drawing = ImageDraw.Draw(chart)
    drawing.line((35, 145, 290, 145), fill="black", width=3)
    drawing.line((35, 145, 35, 20), fill="black", width=3)
    drawing.rectangle((65, 90, 105, 145), fill="steelblue")
    drawing.rectangle((145, 55, 185, 145), fill="steelblue")
    drawing.rectangle((225, 25, 265, 145), fill="steelblue")
    chart_bytes = BytesIO()
    chart.save(chart_bytes, format="PNG")

    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 52), "Quarterly Revenue Evidence", fontsize=18)
    page.insert_image(pymupdf.Rect(72, 90, 396, 272), stream=chart_bytes.getvalue())
    page.insert_text((72, 292), "Figure 1: Revenue grows from Q1 to Q3.", fontsize=10)
    left, top, cell_width, cell_height = 72, 350, 120, 28
    values = (("Quarter", "Revenue"), ("Q1", "10"), ("Q2", "20"), ("Q3", "30"))
    for row_index, row in enumerate(values):
        for column_index, value in enumerate(row):
            x0 = left + column_index * cell_width
            y0 = top + row_index * cell_height
            page.draw_rect(
                pymupdf.Rect(x0, y0, x0 + cell_width, y0 + cell_height),
                color=(0, 0, 0),
                width=1,
            )
            page.insert_text((x0 + 6, y0 + 18), value, fontsize=10)
    return document.tobytes()


@pytest.mark.skipif(
    os.getenv("MM_RAG_RUN_DOCLING_INTEGRATION_TESTS") != "1",
    reason="Docling model integration is opt-in",
)
def test_docling_extracts_visual_and_table_regions(test_settings) -> None:
    extractor = DoclingStructureExtractor(
        test_settings.phase6_docling_artifacts_path,
        image_scale=1.0,
        max_pages=2,
    )

    result = extractor.extract(_synthetic_visual_pdf(), "application/pdf")

    assert result.extractor_name == "docling"
    assert result.regions
    assert all(region.page_number == 1 for region in result.regions)
    assert all(region.page_render.startswith(b"\x89PNG") for region in result.regions)
    assert all(region.crop.startswith(b"\x89PNG") for region in result.regions)
    assert any(region.kind == ContentRegionKind.TABLE for region in result.regions)
    assert any(region.kind != ContentRegionKind.TABLE for region in result.regions)
    table = next(region.table for region in result.regions if region.table is not None)
    assert table.rows
