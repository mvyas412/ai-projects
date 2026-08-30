from collections.abc import Mapping
from typing import Any


def resolve_user_identity(
    backend_user: Mapping[str, Any], oidc_claims: Mapping[str, Any]
) -> tuple[str, str | None]:
    """Choose useful identity copy without exposing tokens or opaque subjects."""

    email = _first_text(backend_user.get("email"), oidc_claims.get("email"))
    display_name = _first_text(
        backend_user.get("display_name"),
        oidc_claims.get("name"),
        oidc_claims.get("nickname"),
        oidc_claims.get("preferred_username"),
        email,
    )
    return display_name or "User", email


def format_activity_details(details: Mapping[str, Any]) -> str:
    """Present useful audit context while hiding implementation identifiers."""

    labels = {
        "chunk_count": "Searchable chunks",
        "citation_count": "Citations",
        "media_type": "File type",
        "name": "Name",
        "role": "Role",
        "target_type": "Scope",
        "title": "Title",
        "version_number": "Version",
    }
    formatted: list[str] = []
    for key, value in details.items():
        if value is None or key == "id" or key.endswith("_id"):
            continue
        label = labels.get(key, key.replace("_", " ").capitalize())
        rendered = str(value).replace("_", " ") if key == "target_type" else str(value)
        formatted.append(f"{label}: {rendered}")
    return " · ".join(formatted) or "Recorded"


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and (normalized := value.strip()):
            return normalized
    return None
