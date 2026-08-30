from typing import Any

import streamlit as st
from utils.api import BackendAPIError
from utils.runtime import api_client, selected_workspace

workspace_id, _ = selected_workspace()
client = api_client()
st.caption("Ask across an authorized workspace, collection, or selected set of documents.")

try:
    documents = client.documents(workspace_id)
    collections = client.collections(workspace_id)
    conversations = client.conversations(workspace_id)
except BackendAPIError as exc:
    st.error(str(exc), icon=":material/error:")
    st.stop()

ready_documents = [
    document
    for document in documents
    if document["latest_version"]["status"] == "ready"
]


@st.dialog("Evidence details", width="large")
def show_evidence(citation: dict[str, Any]) -> None:
    st.subheader(citation["document_title"])
    if citation.get("page_number"):
        st.badge(f"Page {citation['page_number']}", color="blue")
    if citation.get("score") is not None:
        st.caption(f"Retrieval score: {citation['score']:.3f}")
    st.markdown("**Retrieved excerpt**")
    st.write(citation["excerpt"])
    try:
        content, media_type = client.document_content(
            workspace_id,
            citation["document_id"],
            citation["document_version_id"],
        )
        st.download_button(
            "Download original source",
            data=content,
            file_name=citation["document_title"],
            mime=media_type,
            icon=":material/download:",
            type="primary",
        )
    except BackendAPIError as exc:
        st.error(str(exc), icon=":material/error:")


with st.expander("Start a conversation", icon=":material/add_comment:"):
    if not ready_documents:
        st.warning(
            "Index at least one document in Library before starting a grounded conversation.",
            icon=":material/database:",
        )
    else:
        target_label = st.segmented_control(
            "Evidence scope",
            ["Workspace", "Collection", "Documents"],
            default="Workspace",
            key="chat_target_type",
        )
        selected_collection: str | None = None
        selected_documents: list[str] = []
        if target_label == "Collection":
            collection_map = {item["id"]: item["name"] for item in collections}
            if collection_map:
                selected_collection = st.selectbox(
                    "Collection",
                    list(collection_map),
                    format_func=lambda item_id: collection_map[item_id],
                )
            else:
                st.info("Create a collection in Library first.")
        elif target_label == "Documents":
            document_map = {item["id"]: item["title"] for item in ready_documents}
            selected_documents = st.multiselect(
                "Documents",
                list(document_map),
                format_func=lambda item_id: document_map[item_id],
            )

        with st.form("new_conversation", border=False):
            title = st.text_input("Conversation title", placeholder="Quarterly review")
            create = st.form_submit_button(
                "Start conversation", icon=":material/chat:", type="primary"
            )
        if create:
            if target_label == "Collection" and selected_collection is None:
                st.warning("Choose a collection.")
            elif target_label == "Documents" and not selected_documents:
                st.warning("Choose at least one ready document.")
            else:
                try:
                    created = client.create_conversation(
                        workspace_id,
                        title=title,
                        target_type={
                            "Workspace": "workspace",
                            "Collection": "collection",
                            "Documents": "documents",
                        }[target_label or "Workspace"],
                        collection_id=selected_collection,
                        document_ids=selected_documents,
                    )
                    st.session_state["chat_conversation_id"] = created["id"]
                    st.toast("Conversation ready", icon=":material/check:")
                    st.rerun()
                except BackendAPIError as exc:
                    st.error(str(exc), icon=":material/error:")

if not conversations:
    st.info(
        "Start a conversation to ask grounded questions and preserve the answers.",
        icon=":material/forum:",
    )
    st.stop()

conversation_map = {item["id"]: item for item in conversations}
selected_id = st.selectbox(
    "Conversation",
    list(conversation_map),
    format_func=lambda item_id: conversation_map[item_id]["title"],
    key="chat_conversation_id",
)

try:
    conversation = client.conversation(workspace_id, selected_id)
except BackendAPIError as exc:
    st.error(str(exc), icon=":material/error:")
    st.stop()

with st.container(horizontal=True):
    st.badge(conversation["target_type"].capitalize(), color="blue")
    st.caption(f"{conversation['message_count']} persisted messages")

for message in conversation["messages"]:
    with st.chat_message(message["role"]):
        st.write(message["content"])
        if message["role"] == "assistant" and message["citations"]:
            st.caption(f"{len(message['citations'])} supporting source(s)")
            for index, citation in enumerate(message["citations"], start=1):
                label = f"[{index}] {citation['document_title']}"
                if citation.get("page_number"):
                    label += f" · page {citation['page_number']}"
                with st.expander(label, icon=":material/article:"):
                    st.write(citation["excerpt"])
                    if st.button(
                        "Inspect evidence",
                        icon=":material/visibility:",
                        key=f"evidence_{message['id']}_{index}",
                    ):
                        show_evidence(citation)

prompt: str | None = None
if not conversation["messages"]:
    suggestions = {
        "Summarize the key findings": "Summarize the key findings and cite the strongest evidence.",
        "Compare important figures": "Compare the most important figures across the available evidence.",
        "Identify open questions": "What important questions are not answered by the available evidence?",
    }
    selected_suggestion = st.pills(
        "Try asking",
        list(suggestions),
        label_visibility="collapsed",
        key=f"suggestions_{selected_id}",
    )
    if selected_suggestion:
        prompt = suggestions[selected_suggestion]

typed_prompt = st.chat_input(
    "Ask a grounded question",
    submit_mode="disable",
    key=f"prompt_{selected_id}",
)
prompt = typed_prompt or prompt
if prompt:
    try:
        with st.chat_message("user"):
            st.write(prompt)
        with st.chat_message("assistant"):
            with st.status("Searching authorized evidence…", expanded=False):
                client.send_message(workspace_id, selected_id, prompt)
        st.rerun()
    except BackendAPIError as exc:
        st.error(str(exc), icon=":material/error:")
