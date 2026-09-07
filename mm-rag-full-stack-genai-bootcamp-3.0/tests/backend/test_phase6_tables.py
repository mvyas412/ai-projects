import json
from decimal import Decimal
from uuid import uuid4

import pytest

from backend.app.models.table import TableLogicalType, TableValidationState
from backend.app.tables.normalization import (
    normalize_table,
    normalized_table_csv,
    normalized_table_json,
    parse_typed_value,
    table_cell_id,
    table_column_id,
)
from backend.app.visual.extraction import ExtractedTable, ExtractedTableCell


@pytest.mark.parametrize(
    ("raw", "logical_type", "value", "unit", "currency"),
    (
        ("1,234", TableLogicalType.INTEGER, "1234", None, None),
        ("-12.50", TableLogicalType.DECIMAL, "-12.5", None, None),
        ("12.5%", TableLogicalType.PERCENTAGE, "12.5", "%", None),
        ("$1,250.00", TableLogicalType.CURRENCY, "1250", None, "USD"),
        ("18 kg", TableLogicalType.INTEGER, "18", "kg", None),
        ("2026-09-07", TableLogicalType.DATE, "2026-09-07", None, None),
        ("Footnote *", TableLogicalType.TEXT, None, None, None),
    ),
)
def test_typed_values_preserve_raw_meaning(
    raw, logical_type, value, unit, currency
) -> None:
    parsed = parse_typed_value(raw)
    assert parsed.logical_type == logical_type
    assert parsed.value == value
    assert parsed.unit == unit
    assert parsed.currency == currency


def test_multirow_headers_spans_and_exports_are_deterministic() -> None:
    generation, region = uuid4(), uuid4()
    source = ExtractedTable(
        columns=("Year", "North America", "Europe"),
        rows=(("2025", "$1,200", "$900"),),
        cells=(
            ExtractedTableCell(0, 0, 1, 3, "Revenue", column_header=True),
            ExtractedTableCell(1, 0, 1, 1, "Year", column_header=True),
            ExtractedTableCell(1, 1, 1, 1, "North America", column_header=True),
            ExtractedTableCell(1, 2, 1, 1, "Europe", column_header=True),
            ExtractedTableCell(2, 0, 1, 1, "2025"),
            ExtractedTableCell(2, 1, 1, 1, "$1,200"),
            ExtractedTableCell(2, 2, 1, 1, "$900"),
        ),
        row_count=3,
        column_count=3,
        header_row_count=2,
    )

    first = normalize_table(source, generation_id=generation, region_id=region)
    second = normalize_table(source, generation_id=generation, region_id=region)

    assert first == second
    assert first.validation_state == TableValidationState.VALIDATED
    assert first.columns[1].raw_header == "Revenue / North America"
    assert first.columns[1].logical_type == TableLogicalType.CURRENCY
    assert first.cells[-2].header_positions == ((0, 0), (1, 1))
    assert table_column_id(first.table_id, 1) == table_column_id(second.table_id, 1)
    assert table_cell_id(first.table_id, 2, 1) == table_cell_id(second.table_id, 2, 1)
    exported = json.loads(normalized_table_json(first))
    assert exported["structure_sha256"] == first.structure_sha256
    assert normalized_table_csv(first) == (
        b'Revenue,,\nYear,North America,Europe\n2025,"$1,200",$900\n'
    )


def test_malformed_or_excessive_structure_becomes_retrieval_only() -> None:
    malformed = ExtractedTable(
        columns=("Metric", "Value"),
        rows=(("Latency", "15 ms"),),
        cells=(
            ExtractedTableCell(0, 0, 1, 2, "Metrics", column_header=True),
            ExtractedTableCell(1, 0, 1, 2, "Latency"),
            ExtractedTableCell(1, 1, 1, 1, "15 ms"),
        ),
        row_count=2,
        column_count=2,
        header_row_count=1,
    )
    normalized = normalize_table(
        malformed,
        generation_id=uuid4(),
        region_id=uuid4(),
        max_exact_rows=1,
        confidence=0.5,
    )

    assert normalized.validation_state == TableValidationState.RETRIEVAL_ONLY
    assert set(normalized.validation_codes) == {"low_confidence", "overlapping_cells"}


def test_mixed_units_do_not_claim_one_column_unit() -> None:
    source = ExtractedTable(
        columns=("Duration",),
        rows=(("10 ms",), ("2 s",)),
    )
    normalized = normalize_table(source, generation_id=uuid4(), region_id=uuid4())

    assert normalized.validation_state == TableValidationState.VALIDATED
    assert normalized.columns[0].unit is None
    assert Decimal(normalized.cells[1].normalized_value or "0") == Decimal("10")
