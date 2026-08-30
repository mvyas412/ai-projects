import streamlit as st

profile = st.session_state["current_user_profile"]

st.title("Welcome to MM-RAG")
st.caption("Secure, workspace-aware multimodal document intelligence")

with st.container(border=True):
    st.subheader("Your workspaces")
    workspaces = profile["workspaces"]
    if not workspaces:
        st.info("No workspace is available yet.")
    else:
        for workspace in workspaces:
            st.write(f"**{workspace['name']}**")
            st.caption(f"Your role: {workspace['role']}")
