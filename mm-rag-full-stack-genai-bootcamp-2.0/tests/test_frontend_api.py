import httpx
import pytest

from frontend.utils.api import BackendAPIClient, BackendAPIError


def _client() -> BackendAPIClient:
    return BackendAPIClient(base_url="http://backend.test/", access_token="test-token")


def test_api_client_sends_bearer_token_and_expected_path(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def request(method: str, url: str, **kwargs) -> httpx.Response:
        captured.update(method=method, url=url, **kwargs)
        return httpx.Response(
            200,
            json={"workspaces": []},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(httpx, "request", request)
    assert _client().current_user() == {"workspaces": []}
    assert captured["method"] == "GET"
    assert captured["url"] == "http://backend.test/api/v1/users/me"
    assert captured["headers"] == {"Authorization": "Bearer test-token"}


@pytest.mark.parametrize(
    ("status_code", "detail", "expected"),
    [
        (401, "raw provider detail", "Your session is no longer valid"),
        (409, "No indexed document is available", "No indexed document is available"),
        (503, None, "workspace service could not complete"),
    ],
)
def test_api_client_translates_http_failures(
    monkeypatch, status_code: int, detail: str | None, expected: str
) -> None:
    def request(method: str, url: str, **kwargs) -> httpx.Response:
        payload = {"detail": detail} if detail is not None else {}
        return httpx.Response(
            status_code,
            json=payload,
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(httpx, "request", request)
    with pytest.raises(BackendAPIError, match=expected) as error:
        _client().documents("workspace-1")
    assert error.value.status_code == status_code


def test_api_client_hides_network_exception_details(monkeypatch) -> None:
    def request(method: str, url: str, **kwargs) -> httpx.Response:
        raise httpx.ConnectError(
            "secret.internal.example refused connection",
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(httpx, "request", request)
    with pytest.raises(BackendAPIError) as error:
        _client().conversations("workspace-1")
    assert str(error.value) == "The backend is currently unavailable."
    assert "secret.internal" not in str(error.value)
