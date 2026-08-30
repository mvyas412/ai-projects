from typing import Any

import httpx


class BackendAPIError(Exception):
    """Safe frontend-facing backend communication failure."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class BackendAPIClient:
    def __init__(self, *, base_url: str, access_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {access_token}"}

    def current_user(self) -> dict[str, Any]:
        return self._json("GET", "/api/v1/users/me")

    def health_ready(self) -> dict[str, Any]:
        return self._json("GET", "/api/v1/health/ready", authenticated=False)

    def documents(self, workspace_id: str) -> list[dict[str, Any]]:
        return self._json("GET", f"/api/v1/workspaces/{workspace_id}/documents")

    def document(self, workspace_id: str, document_id: str) -> dict[str, Any]:
        return self._json(
            "GET", f"/api/v1/workspaces/{workspace_id}/documents/{document_id}"
        )

    def upload_document(
        self,
        workspace_id: str,
        *,
        filename: str,
        media_type: str,
        content: bytes,
        title: str | None,
    ) -> dict[str, Any]:
        data = {"title": title} if title else None
        return self._json(
            "POST",
            f"/api/v1/workspaces/{workspace_id}/documents",
            data=data,
            files={"file": (filename, content, media_type)},
            timeout=45.0,
        )

    def index_version(
        self, workspace_id: str, document_id: str, version_id: str
    ) -> dict[str, Any]:
        return self._json(
            "POST",
            f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/versions/"
            f"{version_id}/index",
            timeout=180.0,
        )

    def document_content(
        self, workspace_id: str, document_id: str, version_id: str
    ) -> tuple[bytes, str]:
        response = self._request(
            "GET",
            f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/versions/"
            f"{version_id}/content",
            timeout=30.0,
        )
        return response.content, response.headers.get(
            "content-type", "application/octet-stream"
        )

    def collections(self, workspace_id: str) -> list[dict[str, Any]]:
        return self._json("GET", f"/api/v1/workspaces/{workspace_id}/collections")

    def collection(self, workspace_id: str, collection_id: str) -> dict[str, Any]:
        return self._json(
            "GET",
            f"/api/v1/workspaces/{workspace_id}/collections/{collection_id}",
        )

    def create_collection(
        self, workspace_id: str, *, name: str, description: str | None
    ) -> dict[str, Any]:
        return self._json(
            "POST",
            f"/api/v1/workspaces/{workspace_id}/collections",
            json={"name": name, "description": description},
        )

    def add_collection_document(
        self, workspace_id: str, collection_id: str, document_id: str
    ) -> None:
        self._request(
            "PUT",
            f"/api/v1/workspaces/{workspace_id}/collections/{collection_id}/documents/"
            f"{document_id}",
        )

    def conversations(self, workspace_id: str) -> list[dict[str, Any]]:
        return self._json("GET", f"/api/v1/workspaces/{workspace_id}/conversations")

    def activity(self, workspace_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return self._json(
            "GET",
            f"/api/v1/workspaces/{workspace_id}/activity",
            params={"limit": limit},
        )

    def conversation(self, workspace_id: str, conversation_id: str) -> dict[str, Any]:
        return self._json(
            "GET",
            f"/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}",
        )

    def create_conversation(
        self,
        workspace_id: str,
        *,
        title: str,
        target_type: str,
        collection_id: str | None = None,
        document_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._json(
            "POST",
            f"/api/v1/workspaces/{workspace_id}/conversations",
            json={
                "title": title,
                "target_type": target_type,
                "collection_id": collection_id,
                "document_ids": document_ids or [],
            },
        )

    def send_message(
        self, workspace_id: str, conversation_id: str, content: str
    ) -> dict[str, Any]:
        return self._json(
            "POST",
            f"/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/messages",
            json={"content": content},
            timeout=180.0,
        )

    def _json(
        self, method: str, path: str, *, authenticated: bool = True, **kwargs: Any
    ) -> Any:
        return self._request(method, path, authenticated=authenticated, **kwargs).json()

    def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        timeout: float = 10.0,
        **kwargs: Any,
    ) -> httpx.Response:
        try:
            response = httpx.request(
                method,
                f"{self._base_url}{path}",
                headers=self._headers if authenticated else None,
                timeout=timeout,
                **kwargs,
            )
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 401:
                message = "Your session is no longer valid. Please log in again."
            else:
                try:
                    detail = exc.response.json().get("detail")
                except (ValueError, AttributeError):
                    detail = None
                message = (
                    str(detail)
                    if detail
                    else "The workspace service could not complete the request."
                )
            raise BackendAPIError(message, status_code=status_code) from exc
        except httpx.HTTPError as exc:
            raise BackendAPIError("The backend is currently unavailable.") from exc
