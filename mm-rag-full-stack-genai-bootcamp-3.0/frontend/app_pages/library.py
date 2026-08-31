from datetime import datetime
from typing import Literal, cast
from uuid import uuid4

import streamlit as st
from utils.api import BackendAPIError
from utils.runtime import api_client, selected_workspace

workspace_id, workspace = selected_workspace()
client = api_client()
can_write = workspace["role"] in {"owner", "admin", "member"}
st.caption(
    "Upload immutable versions, build the retrieval index, and organize shared knowledge."
)

documents_tab, collections_tab = st.tabs(
    [":material/description: Documents", ":material/folder: Collections"],
    on_change="rerun",
)

if documents_tab.open:
    with documents_tab:
        if can_write:
            expand_upload = bool(st.session_state.pop("library_expand_upload", False))
            with st.expander(
                "Add a document",
                icon=":material/upload_file:",
                expanded=expand_upload,
            ):
                with st.form("library_upload"):
                    uploaded = st.file_uploader(
                        "Document",
                        type=["pdf", "docx", "txt", "md", "png", "jpg", "jpeg"],
                    )
                    title = st.text_input(
                        "Display title",
                        placeholder="Optional — filename is used when blank",
                    )
                    submitted = st.form_submit_button(
                        "Upload document", icon=":material/upload:", type="primary"
                    )
                if submitted:
                    if uploaded is None:
                        st.warning("Choose a document before uploading.")
                    else:
                        try:
                            with st.status("Uploading document…", expanded=True) as status:
                                key = st.session_state.setdefault(
                                    "library_upload_idempotency_key", str(uuid4())
                                )
                                submission = client.upload_document_async(
                                    workspace_id,
                                    filename=uploaded.name,
                                    media_type=uploaded.type or "application/octet-stream",
                                    content=uploaded.getvalue(),
                                    title=title or None,
                                    idempotency_key=key,
                                )
                                status.update(
                                    label="Document queued for processing",
                                    state="complete",
                                    expanded=False,
                                )
                            st.session_state.pop("library_upload_idempotency_key", None)
                            st.session_state["library_document_id"] = submission["document"]["id"]
                            st.toast(
                                "Document is durable and processing asynchronously",
                                icon=":material/check:",
                            )
                            st.rerun()
                        except BackendAPIError as exc:
                            st.error(str(exc), icon=":material/error:")

        try:
            documents = client.documents(workspace_id)
            ingestion_jobs = client.ingestion_jobs(workspace_id)
        except BackendAPIError as exc:
            st.error(str(exc), icon=":material/error:")
            st.stop()

        if not documents:
            st.info(
                "No documents yet. Add the first source to begin building this workspace's knowledge.",
                icon=":material/library_add:",
            )
        else:
            if st.button(
                "Refresh processing status",
                icon=":material/refresh:",
                key="refresh_ingestion_jobs",
            ):
                st.rerun()
            ready = sum(item["latest_version"]["status"] == "ready" for item in documents)
            with st.container(horizontal=True):
                st.badge(f"{len(documents)} documents", color="blue")
                st.badge(f"{ready} ready", color="green" if ready else "gray")

            document_by_id = {item["id"]: item for item in documents}
            selected_id = st.selectbox(
                "Open document",
                list(document_by_id),
                format_func=lambda document_id: document_by_id[document_id]["title"],
                key="library_document_id",
            )
            selected = client.document(workspace_id, selected_id)
            latest_job_by_version: dict[str, dict] = {}
            for job in ingestion_jobs:
                latest_job_by_version.setdefault(job["document_version_id"], job)
            status_value = selected["latest_version"]["status"]
            badge_color = cast(
                Literal["green", "blue", "red", "orange"],
                {
                    "ready": "green",
                    "processing": "blue",
                    "failed": "red",
                }.get(status_value, "orange"),
            )
            with st.container(border=True):
                heading, badge = st.columns([5, 1], vertical_alignment="center")
                heading.subheader(selected["title"])
                badge.badge(status_value.capitalize(), color=badge_color)
                st.caption(
                    f"{selected['original_filename']} · {selected['media_type']} · "
                    f"{len(selected['versions'])} version(s)"
                )

                for version in selected["versions"]:
                    with st.container(border=True):
                        details, actions = st.columns([3, 2], vertical_alignment="center")
                        created_at = datetime.fromisoformat(
                            version["created_at"].replace("Z", "+00:00")
                        )
                        details.markdown(f"**Version {version['version_number']}**")
                        details.caption(
                            f"{version['byte_size'] / 1024:.1f} KB · "
                            f"{created_at:%b %d, %Y at %H:%M} · {version['status']}"
                        )
                        if version.get("failure_reason"):
                            details.error(version["failure_reason"])
                        job = latest_job_by_version.get(version["id"])
                        if job is not None:
                            progress = job["progress"]
                            details.caption(
                                f"Job {job['state'].replace('_', ' ')} · "
                                f"Attempt {progress['attempt_number']} of {job['max_attempts']}"
                            )
                            if progress.get("stage"):
                                details.write(
                                    f":material/progress_activity: "
                                    f"{progress['stage'].replace('_', ' ').capitalize()}"
                                )
                            if progress.get("percentage") is not None:
                                details.progress(
                                    progress["percentage"],
                                    text=f"{progress['percentage']}%",
                                )
                            if job.get("error"):
                                details.warning(job["error"]["summary"])
                        with actions.container(horizontal=True, horizontal_alignment="right"):
                            if can_write and job is None and version["status"] != "ready":
                                if st.button(
                                    "Queue indexing",
                                    icon=":material/database_upload:",
                                    key=f"index_{version['id']}",
                                ):
                                    try:
                                        key_name = f"enqueue_key_{version['id']}"
                                        key = st.session_state.setdefault(
                                            key_name, str(uuid4())
                                        )
                                        client.enqueue_version(
                                            workspace_id,
                                            selected_id,
                                            version["id"],
                                            idempotency_key=key,
                                        )
                                        st.session_state.pop(key_name, None)
                                        st.toast("Indexing job queued", icon=":material/check:")
                                        st.rerun()
                                    except BackendAPIError as exc:
                                        st.error(str(exc), icon=":material/error:")
                            if job is not None and job["state"] in {
                                "pending",
                                "queued",
                                "running",
                                "retry_scheduled",
                            }:
                                if st.button(
                                    "Cancel",
                                    icon=":material/cancel:",
                                    key=f"cancel_{job['id']}",
                                ):
                                    try:
                                        client.cancel_ingestion_job(workspace_id, job["id"])
                                        st.rerun()
                                    except BackendAPIError as exc:
                                        st.error(str(exc), icon=":material/error:")
                            if job is not None and job["state"] in {"failed", "cancelled"}:
                                if st.button(
                                    "Retry",
                                    icon=":material/replay:",
                                    key=f"retry_{job['id']}",
                                ):
                                    try:
                                        key_name = f"retry_key_{job['id']}"
                                        key = st.session_state.setdefault(
                                            key_name, str(uuid4())
                                        )
                                        client.retry_ingestion_job(
                                            workspace_id,
                                            job["id"],
                                            idempotency_key=key,
                                        )
                                        st.session_state.pop(key_name, None)
                                        st.rerun()
                                    except BackendAPIError as exc:
                                        st.error(str(exc), icon=":material/error:")
                            try:
                                content, media_type = client.document_content(
                                    workspace_id, selected_id, version["id"]
                                )
                                st.download_button(
                                    "Download",
                                    data=content,
                                    file_name=selected["original_filename"],
                                    mime=media_type,
                                    icon=":material/download:",
                                    key=f"download_{version['id']}",
                                )
                            except BackendAPIError:
                                st.caption("Source unavailable")

if collections_tab.open:
    with collections_tab:
        try:
            collections = client.collections(workspace_id)
            documents = client.documents(workspace_id)
        except BackendAPIError as exc:
            st.error(str(exc), icon=":material/error:")
            st.stop()

        if can_write:
            with st.expander("Create a collection", icon=":material/create_new_folder:"):
                with st.form("create_collection"):
                    name = st.text_input("Name", placeholder="Board materials")
                    description = st.text_area(
                        "Description", placeholder="Optional purpose or audience"
                    )
                    create = st.form_submit_button(
                        "Create collection",
                        icon=":material/add:",
                        type="primary",
                    )
                if create:
                    try:
                        client.create_collection(
                            workspace_id, name=name, description=description or None
                        )
                        st.toast("Collection created", icon=":material/check:")
                        st.rerun()
                    except BackendAPIError as exc:
                        st.error(str(exc), icon=":material/error:")

        if not collections:
            st.info(
                "Collections group related sources into a focused retrieval scope.",
                icon=":material/folder_open:",
            )
        else:
            collection_map = {item["id"]: item for item in collections}
            collection_id = st.selectbox(
                "Open collection",
                list(collection_map),
                format_func=lambda item_id: collection_map[item_id]["name"],
                key="library_collection_id",
            )
            collection = client.collection(workspace_id, collection_id)
            with st.container(border=True):
                st.subheader(collection["name"])
                st.caption(collection.get("description") or "No description")
                st.badge(f"{collection['document_count']} documents", color="blue")
                if collection["documents"]:
                    for document in collection["documents"]:
                        st.write(f":material/description: {document['title']}")
                else:
                    st.caption("This collection is empty.")

            if can_write and documents:
                candidates = {
                    item["id"]: item
                    for item in documents
                    if item["id"] not in {doc["id"] for doc in collection["documents"]}
                }
                if candidates:
                    with st.form("add_collection_document", border=False):
                        document_id = st.selectbox(
                            "Add a document",
                            list(candidates),
                            format_func=lambda item_id: candidates[item_id]["title"],
                        )
                        add = st.form_submit_button(
                            "Add to collection", icon=":material/add:",
                        )
                    if add:
                        try:
                            client.add_collection_document(
                                workspace_id, collection_id, document_id
                            )
                            st.toast("Document added", icon=":material/check:")
                            st.rerun()
                        except BackendAPIError as exc:
                            st.error(str(exc), icon=":material/error:")
