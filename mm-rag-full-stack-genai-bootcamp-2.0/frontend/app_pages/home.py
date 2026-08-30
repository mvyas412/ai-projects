import streamlit as st
from utils.api import BackendAPIError
from utils.runtime import api_client, selected_workspace

workspace_id, workspace = selected_workspace()
st.caption(
    f"{workspace['name']} · Your role: {str(workspace['role']).capitalize()} · "
    "Secure, workspace-aware document intelligence"
)

summary_slot = st.container()
try:
    client = api_client()
    documents = client.documents(workspace_id)
    collections = client.collections(workspace_id)
    conversations = client.conversations(workspace_id)
except BackendAPIError as exc:
    st.error(str(exc), icon=":material/error:")
    st.stop()

ready_count = sum(
    document["latest_version"]["status"] == "ready" for document in documents
)
with summary_slot:
    metrics = st.columns(4)
    metrics[0].metric("Documents", len(documents), border=True)
    metrics[1].metric("Ready to ask", ready_count, border=True)
    metrics[2].metric("Collections", len(collections), border=True)
    metrics[3].metric("Conversations", len(conversations), border=True)

left, right = st.columns([1.35, 1], gap="large")
with left:
    st.subheader("Continue your work")
    if conversations:
        for conversation in conversations[:4]:
            with st.container(border=True):
                st.markdown(f"**{conversation['title']}**")
                st.caption(
                    f"{conversation['message_count']} messages · "
                    f"{conversation['target_type']} scope"
                )
    else:
        with st.container(border=True):
            st.write("No conversations yet")
            st.caption("Index a document, then start a grounded conversation from Ask.")

with right:
    st.subheader("Library readiness")
    with st.container(border=True):
        if not documents:
            st.write("Your library is ready for its first document.")
            st.caption("Upload PDF, DOCX, text, Markdown, PNG, or JPEG files from Library.")
        else:
            st.write(f"**{ready_count} of {len(documents)}** documents are ready for retrieval.")
            if ready_count < len(documents):
                st.caption("Open Library to index uploaded versions before asking questions.")
            else:
                st.caption("All current document versions are available to grounded chat.")

st.subheader("How evidence moves")
steps = st.columns(3)
with steps[0].container(border=True, height="stretch"):
    st.markdown("**1 · Add knowledge**")
    st.caption("Upload versioned documents and organize them into collections.")
with steps[1].container(border=True, height="stretch"):
    st.markdown("**2 · Build the index**")
    st.caption("The backend extracts content and writes authorization-scoped vectors.")
with steps[2].container(border=True, height="stretch"):
    st.markdown("**3 · Ask with confidence**")
    st.caption("Answers persist with source, page, excerpt, and model metadata.")
