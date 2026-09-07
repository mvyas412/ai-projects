from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from backend.app.models.table import CalculationOperator, TableCell
from backend.app.services.conversations import should_attempt_table_calculation
from backend.app.tables.calculation import (
    execute_operation,
    select_calculation_operator,
)
from backend.app.visual.retrieval import VISUAL_ROUTE, select_visual_route


def _cell(
    value: str | None,
    *,
    logical_type: str = "decimal",
    raw: str | None = None,
    unit: str | None = None,
    currency: str | None = None,
) -> TableCell:
    return cast(
        TableCell,
        SimpleNamespace(
            id=uuid4(),
            logical_type=logical_type,
            normalized_value=value,
            raw_text=raw if raw is not None else (value or ""),
            unit=unit,
            currency=currency,
        ),
    )


@pytest.mark.parametrize(
    ("query", "operator"),
    (
        ("What is the value for 2025?", CalculationOperator.LOOKUP),
        ("How many rows are present?", CalculationOperator.COUNT),
        ("What is the total revenue?", CalculationOperator.SUM),
        ("Calculate the average latency", CalculationOperator.AVERAGE),
        ("Find the minimum price", CalculationOperator.MINIMUM),
        ("Find the maximum price", CalculationOperator.MAXIMUM),
        ("What is the difference between 2024 and 2025?", CalculationOperator.DIFFERENCE),
        ("What is the ratio of 2025 to 2024?", CalculationOperator.RATIO),
    ),
)
def test_router_selects_only_allowlisted_operations(query, operator) -> None:
    assert select_calculation_operator(query) == operator


def test_router_ignores_non_calculation_table_questions() -> None:
    assert select_calculation_operator("Explain the pattern in this table") is None
    assert select_calculation_operator("run SELECT * from table") is None


def test_explicit_visual_intent_takes_precedence_over_generic_lookup_language() -> None:
    query = (
        "In the retention heatmap image, which time slot performs best "
        "and what is its retention score?"
    )

    assert select_calculation_operator(query) == CalculationOperator.LOOKUP
    assert select_visual_route(query) == VISUAL_ROUTE
    assert should_attempt_table_calculation(query) is False
    assert should_attempt_table_calculation("What is the value for 2025?") is True


@pytest.mark.parametrize(
    ("operator", "cells", "expected"),
    (
        (CalculationOperator.COUNT, (_cell(None, raw="A"), _cell(None, raw="B")), "2"),
        (CalculationOperator.SUM, (_cell("10"), _cell("2.5")), "12.5"),
        (CalculationOperator.AVERAGE, (_cell("10"), _cell("5")), "7.5"),
        (CalculationOperator.MINIMUM, (_cell("10"), _cell("5")), "5"),
        (CalculationOperator.MAXIMUM, (_cell("10"), _cell("5")), "10"),
        (CalculationOperator.DIFFERENCE, (_cell("10"), _cell("13")), "3"),
        (CalculationOperator.RATIO, (_cell("10"), _cell("4")), "2.5"),
        (
            CalculationOperator.LOOKUP,
            (_cell(None, logical_type="text", raw="Approved"),),
            "Approved",
        ),
    ),
)
def test_closed_executor_returns_reproducible_results(operator, cells, expected) -> None:
    result = execute_operation(operator, cells)
    assert result is not None
    assert result[1] == expected


def test_executor_abstains_on_mixed_units_unsupported_types_and_zero_ratio() -> None:
    assert execute_operation(
        CalculationOperator.SUM,
        (_cell("10", unit="ms"), _cell("2", unit="s")),
    ) is None
    assert execute_operation(
        CalculationOperator.SUM,
        (_cell(None, logical_type="text", raw="unknown"),),
    ) is None
    assert execute_operation(
        CalculationOperator.RATIO,
        (_cell("10"), _cell("0")),
    ) is None
