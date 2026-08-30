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


if not authentication_is_configured():
    st.title("MM-RAG")
    st.warning("Authentication has not been configured for this environment.")
    st.code("cp .streamlit/secrets.toml.example .streamlit/secrets.toml", language="bash")
    st.caption("Replace the placeholders locally. The resulting secrets file is ignored by Git.")
    st.stop()

if not st.user.is_logged_in:
    st.title("Your documents, grounded answers")
    st.write("Sign in to access your authorized workspaces and documents.")
    st.button(
        "Continue with Auth0",
        icon=":material/login:",
        type="primary",
        on_click=st.login,
        args=("auth0",),
    )
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
    st.error(str(exc))
    st.button("Log out", icon=":material/logout:", on_click=st.logout)
    st.stop()

st.session_state["current_user_profile"] = profile

with st.sidebar:
    display_name = profile["user"].get("display_name") or profile["user"].get("email") or "User"
    st.write(f"Signed in as **{display_name}**")
    st.button("Log out", icon=":material/logout:", on_click=st.logout)

page = st.navigation(
    [st.Page("app_pages/home.py", title="Home", icon=":material/home:")],
    position="top",
)
page.run()
