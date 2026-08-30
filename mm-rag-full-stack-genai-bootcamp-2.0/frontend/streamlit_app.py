from collections.abc import Mapping

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError
from utils.api import BackendAPIClient, BackendAPIError

st.set_page_config(
    page_title="MM-RAG",
    page_icon=":material/document_search:",
    layout="wide",
    initial_sidebar_state="expanded",
)


def authentication_is_configured() -> bool:
    try:
        auth = st.secrets.get("auth")
    except StreamlitSecretNotFoundError:
        return False
    return isinstance(auth, Mapping) and "auth0" in auth


def reset_workspace_state() -> None:
    for key in ("chat_conversation_id", "library_document_id"):
        st.session_state.pop(key, None)


if not authentication_is_configured():
    st.title("MM-RAG")
    st.warning(
        "Authentication has not been configured for this environment.",
        icon=":material/lock:",
    )
    st.code("cp .streamlit/secrets.toml.example .streamlit/secrets.toml", language="bash")
    st.caption("Replace the placeholders locally. The secrets file is ignored by Git.")
    st.stop()

if not st.user.is_logged_in:
    st.title("Your documents. Grounded answers.")
    st.write(
        "A secure multimodal workspace for turning reports, tables, and images "
        "into answers you can verify."
    )
    st.space("small")
    features = st.columns(3)
    with features[0].container(border=True, height="stretch"):
        st.subheader(":material/lock: Private by design")
        st.caption("Workspace authorization protects documents, retrieval, and conversations.")
    with features[1].container(border=True, height="stretch"):
        st.subheader(":material/document_search: Evidence first")
        st.caption("Every grounded answer carries inspectable document and page citations.")
    with features[2].container(border=True, height="stretch"):
        st.subheader(":material/history: Built to resume")
        st.caption("Documents and conversations remain available after you sign out.")
    st.space("medium")
    st.button(
        "Continue securely",
        icon=":material/login:",
        type="primary",
        on_click=st.login,
        args=("auth0",),
    )
    st.caption("Authentication is provided by Auth0. Your password is never handled by MM-RAG.")
    st.stop()

access_token = st.user.tokens.get("access")
if not access_token:
    st.error("Auth0 did not return an API access token. Check the configured audience.")
    st.button("Log out", icon=":material/logout:", on_click=st.logout)
    st.stop()

api_url = str(st.secrets.get("app", {}).get("api_url", "http://127.0.0.1:8000"))
try:
    profile = BackendAPIClient(base_url=api_url, access_token=access_token).current_user()
except BackendAPIError as exc:
    st.error(str(exc), icon=":material/error:")
    st.button("Log out", icon=":material/logout:", on_click=st.logout)
    st.stop()

st.session_state["api_url"] = api_url
st.session_state["current_user_profile"] = profile
workspaces = profile["workspaces"]
if not workspaces:
    st.error("No authorized workspace is available for this account.")
    st.button("Log out", icon=":material/logout:", on_click=st.logout)
    st.stop()

workspace_ids = [workspace["id"] for workspace in workspaces]
if st.session_state.get("selected_workspace_id") not in workspace_ids:
    st.session_state["selected_workspace_id"] = workspace_ids[0]
workspace_names = {workspace["id"]: workspace["name"] for workspace in workspaces}

with st.sidebar:
    st.subheader(":material/document_search: MM-RAG")
    st.selectbox(
        "Workspace",
        workspace_ids,
        format_func=lambda workspace_id: workspace_names[workspace_id],
        key="selected_workspace_id",
        on_change=reset_workspace_state,
    )
    display_name = (
        profile["user"].get("display_name")
        or profile["user"].get("email")
        or "User"
    )
    st.caption(f"Signed in as {display_name}")
    st.button("Log out", icon=":material/logout:", on_click=st.logout)
    st.caption("Phase 2 · Secure workspace intelligence")

page = st.navigation(
    [
        st.Page("app_pages/home.py", title="Overview", icon=":material/home:"),
        st.Page("app_pages/library.py", title="Library", icon=":material/folder:"),
        st.Page("app_pages/chat.py", title="Ask", icon=":material/chat:"),
        st.Page("app_pages/settings.py", title="Settings", icon=":material/settings:"),
    ],
    position="top",
)
st.title(f"{page.icon} {page.title}")
page.run()
