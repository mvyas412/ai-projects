import tomllib
from pathlib import Path

from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_auth0_example_requests_the_custom_api_audience() -> None:
    with (PROJECT_ROOT / ".streamlit" / "secrets.toml.example").open("rb") as config_file:
        auth0 = tomllib.load(config_file)["auth"]["auth0"]

    assert auth0["authorize_params"]["audience"] == "https://api.mm-rag.local"
    assert "audience" not in auth0["client_kwargs"]


def test_streamlit_baseline_starts_without_uncaught_exceptions() -> None:
    app = AppTest.from_file(PROJECT_ROOT / "ui" / "app.py")
    app.run(timeout=45)

    assert not app.exception, [str(exception.value) for exception in app.exception]


def test_authenticated_streamlit_shell_starts_in_a_safe_unauthenticated_state() -> None:
    app = AppTest.from_file(PROJECT_ROOT / "frontend" / "streamlit_app.py")
    app.run(timeout=20)

    assert not app.exception, [str(exception.value) for exception in app.exception]
    warnings = [warning.value for warning in app.warning]
    buttons = [button.label for button in app.button]
    assert (
        "Authentication has not been configured for this environment." in warnings
        or "Continue securely" in buttons
    )
