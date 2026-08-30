import streamlit as st
from utils.api import BackendAPIClient
from utils.presentation import resolve_user_identity


def api_client() -> BackendAPIClient:
    access_token = st.user.tokens.get("access")
    if not access_token:
        raise RuntimeError("The authenticated API access token is unavailable")
    return BackendAPIClient(
        base_url=st.session_state["api_url"], access_token=access_token
    )


def selected_workspace() -> tuple[str, dict[str, object]]:
    profile = st.session_state["current_user_profile"]
    workspaces = profile["workspaces"]
    selected_id = st.session_state["selected_workspace_id"]
    workspace = next(item for item in workspaces if item["id"] == selected_id)
    return selected_id, workspace


def current_user_identity() -> tuple[str, str | None]:
    """Resolve display identity from backend data and safe OIDC profile claims."""

    backend_user = st.session_state["current_user_profile"]["user"]
    # Read only human-facing identity claims; tokens never enter Session State.
    oidc_claims = {
        key: st.user.get(key)
        for key in ("email", "name", "nickname", "preferred_username")
    }
    return resolve_user_identity(backend_user, oidc_claims)
