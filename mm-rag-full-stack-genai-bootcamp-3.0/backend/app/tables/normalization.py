from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import StringIO
from uuid import UUID, uuid5

from backend.app.models.table import (
    TableLogicalType,
    TableValidationState,
)
from backend.app.visual.extraction import ExtractedTable, ExtractedTableCell
from backend.app.visual.provenance import NormalizedBoundingBox

TABLE_SCHEMA_REVISION = "normalized-table-v1"
TABLE_NAMESPACE = UUID("a7a2e578-77bb-4e23-8322-60fe00a2189c")
TABLE_COLUMN_NAMESPACE = UUID("1ad69f91-c024-4726-858d-af509b93761b")
TABLE_CELL_NAMESPACE = UUID("7a5586a8-936f-4cbb-a4d1-c696e3d9bd16")
_INTEGER = re.compile(r"^[+-]?\d{1,3}(?:,\d{3})*$|^[+-]?\d+$")
_DECIMAL = re.compile(r"^[+-]?(?:\d{1,3}(?:,\d{3})*|\d+)\.\d+$")
_PERCENTAGE = re.compile(r"^([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*(?:%|percent)$", re.I)
_CURRENCY = re.compile(
    r"^(?:(USD|EUR|GBP)\s*)?([\$€£])?\s*([+-]?(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?)\s*(USD|EUR|GBP)?$",
    re.I,
)
_NUMBER_UNIT = re.compile(
    r"^([+-]?(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?)\s*"
    r"(kg|g|lb|lbs|ms|s|sec|secs|min|mins|hr|hrs|day|days|kb|mb|gb|tb|m|km)$",
    re.I,
)
_CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}
_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%b %d, %Y", "%B %d, %Y")


class TableNormalizationError(RuntimeError):
    """Raised when an extractor returns no persistable table structure."""


@dataclass(frozen=True, slots=True)
class NormalizedValue:
    logical_type: TableLogicalType
    value: str | None
    normalized_text: str
    unit: str | None = None
    currency: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizedColumn:
    index: int
    raw_header: str
    normalized_header: str
    logical_type: TableLogicalType
    unit: str | None
    currency: str | None


@dataclass(frozen=True, slots=True)
class NormalizedCell:
    row_index: int
    column_index: int
    row_span: int
    column_span: int
    is_header: bool
    header_positions: tuple[tuple[int, int], ...]
    raw_text: str
    normalized_text: str
    logical_type: TableLogicalType
    normalized_value: str | None
    unit: str | None
    currency: str | None
    bbox: NormalizedBoundingBox | None


@dataclass(frozen=True, slots=True)
class NormalizedTable:
    table_id: UUID
    region_id: UUID
    row_count: int
    column_count: int
    header_row_count: int
    columns: tuple[NormalizedColumn, ...]
    cells: tuple[NormalizedCell, ...]
    validation_state: TableValidationState
    validation_codes: tuple[str, ...]
    structure_sha256: str


def normalize_table(
    table: ExtractedTable,
    *,
    generation_id: UUID,
    region_id: UUID,
    max_exact_rows: int = 1000,
    max_columns: int = 100,
    confidence: float | None = None,
) -> NormalizedTable:
    cells = tuple(table.cells) or _fallback_cells(table)
    row_count = table.row_count or max(
        (cell.row_index + cell.row_span for cell in cells), default=0
    )
    column_count = table.column_count or max(
        (cell.column_index + cell.column_span for cell in cells), default=0
    )
    if row_count <= 0 or column_count <= 0 or not cells:
        raise TableNormalizationError("Extractor returned no persistable table structure")
    header_row_count = min(max(table.header_row_count, 0), row_count)
    validation_codes = _validate_grid(
        cells,
        row_count=row_count,
        column_count=column_count,
        header_row_count=header_row_count,
        max_exact_rows=max_exact_rows,
        max_columns=max_columns,
        confidence=confidence,
    )
    normalized_cells = tuple(
        _normalize_cell(cell, cells, header_row_count) for cell in cells
    )
    columns = tuple(
        _normalize_column(index, table, normalized_cells, header_row_count)
        for index in range(column_count)
    )
    canonical = {
        "schema_revision": TABLE_SCHEMA_REVISION,
        "region_id": str(region_id),
        "rows": row_count,
        "columns": column_count,
        "header_rows": header_row_count,
        "column_contracts": [_jsonable(asdict(column)) for column in columns],
        "cells": [_jsonable(asdict(cell)) for cell in normalized_cells],
        "validation_codes": sorted(validation_codes),
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    structure_sha256 = hashlib.sha256(encoded).hexdigest()
    table_id = uuid5(TABLE_NAMESPACE, f"{generation_id}:{region_id}:{structure_sha256}")
    return NormalizedTable(
        table_id=table_id,
        region_id=region_id,
        row_count=row_count,
        column_count=column_count,
        header_row_count=header_row_count,
        columns=columns,
        cells=normalized_cells,
        validation_state=(
            TableValidationState.VALIDATED
            if not validation_codes
            else TableValidationState.RETRIEVAL_ONLY
        ),
        validation_codes=tuple(sorted(validation_codes)),
        structure_sha256=structure_sha256,
    )


def table_column_id(table_id: UUID, column_index: int) -> UUID:
    return uuid5(TABLE_COLUMN_NAMESPACE, f"{table_id}:{column_index}")


def table_cell_id(table_id: UUID, row_index: int, column_index: int) -> UUID:
    return uuid5(TABLE_CELL_NAMESPACE, f"{table_id}:{row_index}:{column_index}")


def normalized_table_json(table: NormalizedTable) -> bytes:
    payload = {
        "schema_revision": TABLE_SCHEMA_REVISION,
        "table_id": str(table.table_id),
        "region_id": str(table.region_id),
        "row_count": table.row_count,
        "column_count": table.column_count,
        "header_row_count": table.header_row_count,
        "structure_sha256": table.structure_sha256,
        "validation_state": table.validation_state.value,
        "validation_codes": table.validation_codes,
        "columns": [_jsonable(asdict(column)) for column in table.columns],
        "cells": [_jsonable(asdict(cell)) for cell in table.cells],
    }
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def normalized_table_csv(table: NormalizedTable) -> bytes:
    grid = [["" for _ in range(table.column_count)] for _ in range(table.row_count)]
    for cell in table.cells:
        grid[cell.row_index][cell.column_index] = cell.raw_text
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(grid)
    return output.getvalue().encode("utf-8")


def parse_typed_value(raw: str) -> NormalizedValue:
    text = " ".join(raw.strip().split())
    if not text:
        return NormalizedValue(TableLogicalType.TEXT, None, "")
    percentage = _PERCENTAGE.fullmatch(text)
    if percentage:
        value = _decimal_string(percentage.group(1))
        return NormalizedValue(TableLogicalType.PERCENTAGE, value, text, unit="%")
    currency = _CURRENCY.fullmatch(text)
    if currency and (currency.group(1) or currency.group(2) or currency.group(4)):
        prefix, symbol, amount, suffix = currency.groups()
        code = (prefix or suffix or _CURRENCY_SYMBOLS.get(symbol or "", "")).upper()
        if prefix and suffix and prefix.upper() != suffix.upper():
            return NormalizedValue(TableLogicalType.TEXT, None, text)
        if symbol and code != _CURRENCY_SYMBOLS[symbol]:
            return NormalizedValue(TableLogicalType.TEXT, None, text)
        return NormalizedValue(
            TableLogicalType.CURRENCY,
            _decimal_string(amount),
            text,
            currency=code,
        )
    number_unit = _NUMBER_UNIT.fullmatch(text)
    if number_unit:
        amount, unit = number_unit.groups()
        logical_type = TableLogicalType.DECIMAL if "." in amount else TableLogicalType.INTEGER
        return NormalizedValue(
            logical_type,
            _decimal_string(amount),
            text,
            unit=unit.casefold(),
        )
    if _INTEGER.fullmatch(text):
        return NormalizedValue(
            TableLogicalType.INTEGER, _decimal_string(text), text
        )
    if _DECIMAL.fullmatch(text):
        return NormalizedValue(
            TableLogicalType.DECIMAL, _decimal_string(text), text
        )
    for date_format in _DATE_FORMATS:
        try:
            value = datetime.strptime(text, date_format).date().isoformat()
            return NormalizedValue(TableLogicalType.DATE, value, text)
        except ValueError:
            continue
    return NormalizedValue(TableLogicalType.TEXT, None, text.casefold())


def _fallback_cells(table: ExtractedTable) -> tuple[ExtractedTableCell, ...]:
    cells = [
        ExtractedTableCell(0, index, 1, 1, header, column_header=True)
        for index, header in enumerate(table.columns)
    ]
    cells.extend(
        ExtractedTableCell(row_index, column_index, 1, 1, value)
        for row_index, row in enumerate(table.rows, start=1)
        for column_index, value in enumerate(row)
    )
    return tuple(cells)


def _validate_grid(
    cells: tuple[ExtractedTableCell, ...],
    *,
    row_count: int,
    column_count: int,
    header_row_count: int,
    max_exact_rows: int,
    max_columns: int,
    confidence: float | None,
) -> set[str]:
    failures: set[str] = set()
    if header_row_count == 0:
        failures.add("missing_header")
    if row_count - header_row_count > max_exact_rows:
        failures.add("row_limit_exceeded")
    if column_count > max_columns:
        failures.add("column_limit_exceeded")
    if confidence is not None and confidence < 0.7:
        failures.add("low_confidence")
    occupied: set[tuple[int, int]] = set()
    origins: set[tuple[int, int]] = set()
    for cell in cells:
        origin = (cell.row_index, cell.column_index)
        if origin in origins:
            failures.add("duplicate_cell_origin")
        origins.add(origin)
        if (
            cell.row_index < 0
            or cell.column_index < 0
            or cell.row_span <= 0
            or cell.column_span <= 0
            or cell.row_index + cell.row_span > row_count
            or cell.column_index + cell.column_span > column_count
        ):
            failures.add("cell_out_of_bounds")
            continue
        for row in range(cell.row_index, cell.row_index + cell.row_span):
            for column in range(cell.column_index, cell.column_index + cell.column_span):
                if (row, column) in occupied:
                    failures.add("overlapping_cells")
                occupied.add((row, column))
    if len(occupied) != row_count * column_count:
        failures.add("incomplete_grid")
    return failures


def _normalize_cell(
    cell: ExtractedTableCell,
    cells: tuple[ExtractedTableCell, ...],
    header_row_count: int,
) -> NormalizedCell:
    is_header = cell.column_header or cell.row_header or cell.row_index < header_row_count
    value = (
        NormalizedValue(TableLogicalType.TEXT, None, " ".join(cell.text.strip().split()))
        if is_header
        else parse_typed_value(cell.text)
    )
    headers = tuple(
        sorted(
            (header.row_index, header.column_index)
            for header in cells
            if (
                (
                    (header.column_header or header.row_index < header_row_count)
                    and header.column_index <= cell.column_index
                    and header.column_index + header.column_span > cell.column_index
                )
                or (
                    header.row_header
                    and header.row_index <= cell.row_index
                    and header.row_index + header.row_span > cell.row_index
                )
            )
        )
    )
    return NormalizedCell(
        row_index=cell.row_index,
        column_index=cell.column_index,
        row_span=cell.row_span,
        column_span=cell.column_span,
        is_header=is_header,
        header_positions=() if is_header else headers,
        raw_text=cell.text,
        normalized_text=value.normalized_text,
        logical_type=value.logical_type,
        normalized_value=value.value,
        unit=value.unit,
        currency=value.currency,
        bbox=cell.bbox,
    )


def _normalize_column(
    index: int,
    table: ExtractedTable,
    cells: tuple[NormalizedCell, ...],
    header_row_count: int,
) -> NormalizedColumn:
    header_parts = [
        cell.raw_text
        for cell in cells
        if cell.is_header
        and cell.row_index < header_row_count
        and cell.column_index <= index < cell.column_index + cell.column_span
        and cell.raw_text.strip()
    ]
    raw_header = " / ".join(header_parts) or (
        table.columns[index] if index < len(table.columns) else f"Column {index + 1}"
    )
    values = [
        cell
        for cell in cells
        if not cell.is_header and cell.column_index == index and cell.normalized_text
    ]
    logical_type = _column_type(values)
    units = {cell.unit for cell in values if cell.unit}
    currencies = {cell.currency for cell in values if cell.currency}
    return NormalizedColumn(
        index=index,
        raw_header=raw_header,
        normalized_header=" ".join(raw_header.casefold().split()),
        logical_type=logical_type,
        unit=next(iter(units)) if len(units) == 1 else None,
        currency=next(iter(currencies)) if len(currencies) == 1 else None,
    )


def _column_type(cells: list[NormalizedCell]) -> TableLogicalType:
    kinds = {cell.logical_type for cell in cells}
    if not kinds:
        return TableLogicalType.TEXT
    if kinds <= {TableLogicalType.INTEGER, TableLogicalType.DECIMAL}:
        return (
            TableLogicalType.DECIMAL
            if TableLogicalType.DECIMAL in kinds
            else TableLogicalType.INTEGER
        )
    return next(iter(kinds)) if len(kinds) == 1 else TableLogicalType.TEXT


def _decimal_string(value: str) -> str:
    try:
        decimal = Decimal(value.replace(",", ""))
    except InvalidOperation as exc:
        raise TableNormalizationError("A numeric table value could not be normalized") from exc
    normalized = format(decimal.normalize(), "f")
    return "0" if normalized in {"-0", ""} else normalized


def _jsonable(value):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, TableLogicalType | TableValidationState):
        return value.value
    if isinstance(value, NormalizedBoundingBox):
        return asdict(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
