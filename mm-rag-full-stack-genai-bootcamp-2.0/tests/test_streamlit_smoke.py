from pathlib import Path

from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_streamlit_baseline_starts_without_uncaught_exceptions() -> None:
    app = AppTest.from_file(PROJECT_ROOT / "ui" / "app.py")
    app.run(timeout=45)

    assert not app.exception, [str(exception.value) for exception in app.exception]
