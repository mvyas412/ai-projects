import streamlit as st
from utils.api import BackendAPIError
from utils.runtime import api_client, selected_workspace

_, workspace = selected_workspace()
profile = st.session_state["current_user_profile"]
st.caption("Review your session, workspace access, and service readiness.")

identity, access = st.columns(2, gap="large")
with identity.container(border=True, height="stretch"):
    st.subheader("Account")
    st.write(profile["user"].get("display_name") or "User")
    st.caption(profile["user"].get("email") or "Email not provided")
    st.badge("Authenticated", icon=":material/verified_user:", color="green")

with access.container(border=True, height="stretch"):
    st.subheader("Current workspace")
    st.write(workspace["name"])
    st.caption("Access is enforced by FastAPI for every document and conversation request.")
    st.badge(str(workspace["role"]).capitalize(), color="blue")

st.subheader("Service readiness")
try:
    readiness = api_client().health_ready()
    with st.container(border=True):
        state = readiness.get("status", "unknown")
        st.badge(
            str(state).capitalize(),
            icon=":material/check_circle:" if state == "ready" else ":material/warning:",
            color="green" if state == "ready" else "orange",
        )
        for name, component in readiness.get("components", {}).items():
            st.write(f"**{name.capitalize()}** · {component.get('status', 'unknown')}")
except BackendAPIError as exc:
    st.error(str(exc), icon=":material/error:")

with st.expander("Privacy and security", icon=":material/security:"):
    st.write(
        "MM-RAG keeps API credentials outside the browser application, validates Auth0 "
        "tokens at the backend, and constructs retrieval filters only from authorized "
        "workspace records."
    )
    st.caption("Access tokens and local secrets are not displayed or persisted as product data.")
