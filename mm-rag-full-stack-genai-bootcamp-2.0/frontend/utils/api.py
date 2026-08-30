from typing import Any

import httpx


class BackendAPIError(Exception):
    """Safe frontend-facing backend communication failure."""


class BackendAPIClient:
    def __init__(self, *, base_url: str, access_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {access_token}"}

    def current_user(self) -> dict[str, Any]:
        try:
            response = httpx.get(
                f"{self._base_url}/api/v1/users/me",
                headers=self._headers,
                timeout=5.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                raise BackendAPIError(
                    "Your session is no longer valid. Please log in again."
                ) from exc
            raise BackendAPIError("The workspace service could not complete the request.") from exc
        except httpx.HTTPError as exc:
            raise BackendAPIError("The backend is currently unavailable.") from exc
        return response.json()
