from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from backend.app.models.table import (
    CalculationOperator,
    CalculationTrace,
    TableCell,
    TableColumn,
    TableLogicalType,
    TableRegion,
    TableValidationState,
)

CALCULATION_OPERATOR_REVISION = "closed-table-operations-v1"
CALCULATION_ROUTER_REVISION = "table-calculation-router-v1"
_OPERATOR_PATTERNS = (
    (CalculationOperator.AVERAGE, re.compile(r"\b(?:average|mean)\b", re.I)),
    (CalculationOperator.MINIMUM, re.compile(r"\b(?:minimum|min|smallest|lowest)\b", re.I)),
    (CalculationOperator.MAXIMUM, re.compile(r"\b(?:maximum|max|largest|highest)\b", re.I)),
    (CalculationOperator.DIFFERENCE, re.compile(r"\b(?:difference|subtract)\b", re.I)),
    (CalculationOperator.RATIO, re.compile(r"\b(?:ratio|divided by)\b", re.I)),
    (CalculationOperator.SUM, re.compile(r"\b(?:sum|total)\b", re.I)),
    (CalculationOperator.COUNT, re.compile(r"\b(?:count|how many)\b", re.I)),
    (CalculationOperator.LOOKUP, re.compile(r"\b(?:lookup|value|what is|which)\b", re.I)),
)
_NUMERIC_TYPES = {
    TableLogicalType.INTEGER.value,
    TableLogicalType.DECIMAL.value,
    TableLogicalType.PERCENTAGE.value,
    TableLogicalType.CURRENCY.value,
}


@dataclass(frozen=True, slots=True)
class TableCalculationScope:
    document_id: UUID
    document_version_id: UUID
    generation_id: UUID
    document_title: str


@dataclass(frozen=True, slots=True)
class TableCalculationRequest:
    workspace_id: UUID
    documents: tuple[TableCalculationScope, ...]
    query: str


@dataclass(frozen=True, slots=True)
class CalculationEvidence:
    trace_id: UUID
    operator: CalculationOperator
    document_id: UUID
    document_version_id: UUID
    generation_id: UUID
    document_title: str
    page_number: int
    region_id: UUID
    table_id: UUID
    cell_ids: tuple[UUID, ...]
    operand_values: tuple[str, ...]
    unit: str | None
    currency: str | None
    result_type: str
    result_value: str
    rounding_rule: str


@dataclass(frozen=True, slots=True)
class CalculationDecision:
    operator: CalculationOperator | None
    evidence: CalculationEvidence | None

    @property
    def attempted(self) -> bool:
        return self.operator is not None


@dataclass(frozen=True, slots=True)
class _TableData:
    table: TableRegion
    document_title: str
    columns: tuple[TableColumn, ...]
    cells: tuple[TableCell, ...]


class PostgresTableCalculationEngine:
    """Resolve and execute only the closed, application-authored table plan."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def calculate(self, request: TableCalculationRequest) -> CalculationDecision:
        operator = select_calculation_operator(request.query)
        if operator is None:
            return CalculationDecision(None, None)
        if not request.documents or len(request.documents) > 100:
            return CalculationDecision(operator, None)
        tables = self._authorized_tables(request)
        selected = _select_table(tables, request.query)
        if selected is None:
            return CalculationDecision(operator, None)
        operands = _resolve_operands(selected, operator, request.query)
        if operands is None:
            return CalculationDecision(operator, None)
        calculated = execute_operation(operator, operands)
        if calculated is None:
            return CalculationDecision(operator, None)
        result_type, result_value, unit, currency, rounding_rule = calculated
        trace = CalculationTrace(
            workspace_id=request.workspace_id,
            document_id=selected.table.document_id,
            document_version_id=selected.table.document_version_id,
            generation_id=selected.table.generation_id,
            table_id=selected.table.id,
            region_id=selected.table.region_id,
            table_creation_attempt_id=selected.table.creation_attempt_id,
            operator=operator.value,
            operator_revision=CALCULATION_OPERATOR_REVISION,
            cell_ids=[str(cell.id) for cell in operands],
            operand_types=[cell.logical_type for cell in operands],
            operand_values=[_operand_value(cell) for cell in operands],
            unit=unit,
            currency=currency,
            rounding_rule=rounding_rule,
            result_type=result_type,
            result_value=result_value,
            query_fingerprint=_query_fingerprint(request.query),
        )
        self._session.add(trace)
        self._session.flush()
        return CalculationDecision(
            operator,
            CalculationEvidence(
                trace_id=trace.id,
                operator=operator,
                document_id=selected.table.document_id,
                document_version_id=selected.table.document_version_id,
                generation_id=selected.table.generation_id,
                document_title=selected.document_title,
                page_number=selected.table.page_number,
                region_id=selected.table.region_id,
                table_id=selected.table.id,
                cell_ids=tuple(cell.id for cell in operands),
                operand_values=tuple(_operand_value(cell) for cell in operands),
                unit=unit,
                currency=currency,
                result_type=result_type,
                result_value=result_value,
                rounding_rule=rounding_rule,
            ),
        )

    def _authorized_tables(self, request: TableCalculationRequest) -> tuple[_TableData, ...]:
        identities = {
            (scope.document_id, scope.document_version_id, scope.generation_id)
            for scope in request.documents
        }
        if len(identities) != len(request.documents):
            return ()
        scope_by_identity = {
            (scope.document_id, scope.document_version_id, scope.generation_id): scope
            for scope in request.documents
        }
        conditions = [
            and_(
                TableRegion.document_id == document_id,
                TableRegion.document_version_id == version_id,
                TableRegion.generation_id == generation_id,
            )
            for document_id, version_id, generation_id in identities
        ]
        rows = tuple(
            self._session.scalars(
                select(TableRegion)
                .where(
                    TableRegion.workspace_id == request.workspace_id,
                    TableRegion.validation_state == TableValidationState.VALIDATED.value,
                    or_(*conditions),
                )
                .order_by(TableRegion.id)
            )
        )
        result: list[_TableData] = []
        for table in rows:
            identity = (table.document_id, table.document_version_id, table.generation_id)
            scope = scope_by_identity.get(identity)
            if scope is None:
                continue
            columns = tuple(
                self._session.scalars(
                    select(TableColumn)
                    .where(
                        TableColumn.workspace_id == request.workspace_id,
                        TableColumn.table_id == table.id,
                        TableColumn.generation_id == table.generation_id,
                    )
                    .order_by(TableColumn.column_index)
                )
            )
            cells = tuple(
                self._session.scalars(
                    select(TableCell)
                    .where(
                        TableCell.workspace_id == request.workspace_id,
                        TableCell.table_id == table.id,
                        TableCell.generation_id == table.generation_id,
                    )
                    .order_by(TableCell.row_index, TableCell.column_index)
                )
            )
            if len(columns) == table.column_count and cells:
                result.append(_TableData(table, scope.document_title, columns, cells))
        return tuple(result)


def select_calculation_operator(query: str) -> CalculationOperator | None:
    normalized = " ".join(query.split())
    for operator, pattern in _OPERATOR_PATTERNS:
        if pattern.search(normalized):
            return operator
    return None


def format_calculation_answer(evidence: CalculationEvidence) -> str:
    value = evidence.result_value
    if evidence.currency:
        value = f"{evidence.currency} {value}"
    elif evidence.unit == "%":
        value = f"{value}%"
    elif evidence.unit:
        value = f"{value} {evidence.unit}"
    return f"The exact {evidence.operator.value} from the validated table is {value}."


def _select_table(tables: tuple[_TableData, ...], query: str) -> _TableData | None:
    if not tables:
        return None
    normalized = _normalize(query)
    scored = [(table, _table_score(table, normalized)) for table in tables]
    best = max(score for _, score in scored)
    candidates = [table for table, score in scored if score == best]
    return candidates[0] if len(candidates) == 1 else None


def _table_score(data: _TableData, query: str) -> int:
    phrases = {
        part.strip()
        for column in data.columns
        for part in column.normalized_header.split("/")
        if len(part.strip()) >= 2
    }
    phrases.update(
        cell.normalized_text
        for cell in data.cells
        if not cell.is_header and cell.column_index == 0 and len(cell.normalized_text) >= 2
    )
    return sum(1 for phrase in phrases if _phrase_position(query, phrase) is not None)


def _resolve_operands(
    data: _TableData,
    operator: CalculationOperator,
    query: str,
) -> tuple[TableCell, ...] | None:
    normalized_query = _normalize(query)
    column = _select_column(data.columns, normalized_query, operator)
    data_cells = tuple(cell for cell in data.cells if not cell.is_header)
    if operator == CalculationOperator.COUNT and column is None and re.search(
        r"\brows?\b", normalized_query
    ):
        labels = tuple(cell for cell in data_cells if cell.column_index == 0)
        return labels or None
    if column is None:
        return None
    column_cells = tuple(cell for cell in data_cells if cell.column_index == column.column_index)
    if operator == CalculationOperator.LOOKUP:
        rows = _mentioned_rows(data_cells, normalized_query)
        if not rows:
            rows = sorted({cell.row_index for cell in data_cells})
            if len(rows) != 1:
                return None
        if len(rows) != 1:
            return None
        matches = tuple(cell for cell in column_cells if cell.row_index == rows[0])
        return matches if len(matches) == 1 else None
    if operator in {CalculationOperator.DIFFERENCE, CalculationOperator.RATIO}:
        rows = _mentioned_rows(data_cells, normalized_query)
        if len(rows) != 2:
            return None
        resolved_cells: list[TableCell] = []
        for row in rows:
            cell = next((item for item in column_cells if item.row_index == row), None)
            if cell is None:
                return None
            resolved_cells.append(cell)
        return tuple(resolved_cells)
    return column_cells or None


def _select_column(
    columns: tuple[TableColumn, ...],
    query: str,
    operator: CalculationOperator,
) -> TableColumn | None:
    scored: list[tuple[TableColumn, int]] = []
    for column in columns:
        phrases = [part.strip() for part in column.normalized_header.split("/")]
        score = sum(1 for phrase in phrases if phrase and _phrase_position(query, phrase) is not None)
        scored.append((column, score))
    best = max((score for _, score in scored), default=0)
    if best:
        matches = [column for column, score in scored if score == best]
        return matches[0] if len(matches) == 1 else None
    candidates = [
        column
        for column in columns
        if operator == CalculationOperator.COUNT or column.logical_type in _NUMERIC_TYPES
    ]
    return candidates[0] if len(candidates) == 1 else None


def _mentioned_rows(cells: tuple[TableCell, ...], query: str) -> list[int]:
    labels = [
        cell
        for cell in cells
        if cell.column_index == 0 and cell.normalized_text
    ]
    found = [
        (position, cell.row_index)
        for cell in labels
        if (position := _phrase_position(query, cell.normalized_text)) is not None
    ]
    return [row for _, row in sorted(found)]


def execute_operation(
    operator: CalculationOperator,
    cells: tuple[TableCell, ...],
) -> tuple[str, str, str | None, str | None, str] | None:
    if operator == CalculationOperator.LOOKUP:
        cell = cells[0]
        value = cell.normalized_value if cell.normalized_value is not None else cell.raw_text
        return cell.logical_type, value, cell.unit, cell.currency, "source-value-no-rounding-v1"
    if operator == CalculationOperator.COUNT:
        return (
            TableLogicalType.INTEGER.value,
            str(len(cells)),
            None,
            None,
            "integer-count-v1",
        )
    if any(
        cell.logical_type not in _NUMERIC_TYPES or cell.normalized_value is None
        for cell in cells
    ):
        return None
    compatibility = {(cell.unit, cell.currency, _numeric_family(cell)) for cell in cells}
    if len(compatibility) != 1:
        return None
    unit, currency, family = next(iter(compatibility))
    try:
        values = tuple(Decimal(cell.normalized_value or "") for cell in cells)
    except InvalidOperation:
        return None
    if operator == CalculationOperator.SUM:
        result = sum(values, Decimal(0))
        rounding = "exact-decimal-v1"
    elif operator == CalculationOperator.AVERAGE:
        result = (sum(values, Decimal(0)) / Decimal(len(values))).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_EVEN
        )
        rounding = "six-decimal-half-even-v1"
    elif operator == CalculationOperator.MINIMUM:
        result = min(values)
        rounding = "exact-decimal-v1"
    elif operator == CalculationOperator.MAXIMUM:
        result = max(values)
        rounding = "exact-decimal-v1"
    elif operator == CalculationOperator.DIFFERENCE and len(values) == 2:
        result = abs(values[0] - values[1])
        rounding = "absolute-exact-decimal-v1"
    elif operator == CalculationOperator.RATIO and len(values) == 2 and values[1] != 0:
        result = (values[0] / values[1]).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_EVEN
        )
        unit, currency = None, None
        family = TableLogicalType.DECIMAL.value
        rounding = "six-decimal-half-even-v1"
    else:
        return None
    return family, _decimal_string(result), unit, currency, rounding


def _numeric_family(cell: TableCell) -> str:
    if cell.logical_type in {TableLogicalType.INTEGER.value, TableLogicalType.DECIMAL.value}:
        return TableLogicalType.DECIMAL.value
    return cell.logical_type


def _operand_value(cell: TableCell) -> str:
    return cell.normalized_value if cell.normalized_value is not None else cell.raw_text


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _phrase_position(query: str, phrase: str) -> int | None:
    match = re.search(rf"(?<!\w){re.escape(_normalize(phrase))}(?!\w)", query)
    return match.start() if match else None


def _query_fingerprint(query: str) -> str:
    return hashlib.sha256(_normalize(query).encode("utf-8")).hexdigest()


def _decimal_string(value: Decimal) -> str:
    normalized = format(value.normalize(), "f")
    return "0" if normalized in {"-0", ""} else normalized
