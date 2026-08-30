from pathlib import Path

from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_streamlit_baseline_starts_without_uncaught_exceptions() -> None:
    app = AppTest.from_file(PROJECT_ROOT / "ui" / "app.py")
    app.run(timeout=45)

    assert not app.exception, [str(exception.value) for exception in app.exception]


def test_authenticated_streamlit_shell_shows_safe_setup_state_without_secrets() -> None:
    app = AppTest.from_file(PROJECT_ROOT / "frontend" / "streamlit_app.py")
    app.run(timeout=20)

    assert not app.exception, [str(exception.value) for exception in app.exception]
    assert "Authentication has not been configured" in app.warning[0].value
