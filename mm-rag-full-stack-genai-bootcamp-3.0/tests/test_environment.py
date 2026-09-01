from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "module_name",
    [
        "alembic",
        "boto3",
        "fastapi",
        "fastembed",
        "langchain_core",
        "langchain_openai",
        "langchain_qdrant",
        "langchain_text_splitters",
        "pandas",
        "pdfplumber",
        "PIL",
        "psycopg",
        "pydantic_settings",
        "pymupdf",
        "pytesseract",
        "qdrant_client",
        "sqlalchemy",
        "streamlit",
        "structlog",
        "uvicorn",
    ],
)
def test_runtime_dependency_is_importable(module_name: str) -> None:
    importlib.import_module(module_name)


def test_python_runtime_is_supported() -> None:
    assert sys.version_info[:2] == (3, 12)


def test_tests_run_from_the_phase_3_environment() -> None:
    expected_environment = (PROJECT_ROOT / ".venv").resolve()
    active_environment = Path(sys.prefix).resolve()
    assert active_environment == expected_environment, (
        f"Expected the Phase 3 environment at {expected_environment}, got {active_environment}"
    )
