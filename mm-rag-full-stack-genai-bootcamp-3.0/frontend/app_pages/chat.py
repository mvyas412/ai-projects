from html import escape
from io import BytesIO
from typing import Any

import streamlit as st
from PIL import Image, ImageDraw
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
def show_evidence(
    citation: dict[str, Any],
    message_id: str,
    citation_index: int,
) -> None:
    try:
        with st.spinner("Resolving current authorized evidence…"):
            evidence = client.evidence(
                workspace_id,
                selected_id,
                message_id,
                citation_index,
            )
    except BackendAPIError as exc:
        if exc.status_code == 404:
            st.warning(
                "This evidence is no longer available in your current access scope.",
                icon=":material/lock:",
            )
        else:
            st.error(str(exc), icon=":material/error:")
        return

    st.subheader(evidence["document_title"])
    with st.container(horizontal=True):
        st.badge(evidence["evidence_kind"].replace("_", " ").title(), color="blue")
        if evidence.get("page_number"):
            st.badge(f"Page {evidence['page_number']}", color="gray")
        if citation.get("score") is not None:
            st.caption(f"Retrieval score: {citation['score']:.3f}")
    st.markdown("**Retrieved evidence label**")
    st.write(evidence["excerpt"])

    region = evidence.get("region")
    if region:
        st.caption(
            "The outlined area below is the exact stored source region for this citation."
        )
        _show_region_evidence(evidence, message_id, citation_index)
    else:
        st.info(
            "This is text evidence from an earlier-compatible citation; no visual region "
            "was attached.",
            icon=":material/article:",
        )

    if evidence.get("table"):
        st.markdown("### Structured table")
        st.caption(
            "Cells marked CITED are the exact operands or values supporting this answer."
        )
        st.markdown(_table_html(evidence["table"]), unsafe_allow_html=True)

    calculation = evidence.get("calculation")
    if calculation:
        st.markdown("### Exact calculation")
        result = _display_value(
            calculation["result_value"],
            calculation.get("unit"),
            calculation.get("currency"),
        )
        st.metric(calculation["operator"].replace("_", " ").title(), result)
        for operand in calculation["operands"]:
            st.write(f"- {operand['label']}: `{operand['value']}`")
        st.caption(
            f"Rule: {calculation['operator_revision']} · "
            f"Rounding: {calculation['rounding_rule']}"
        )

    try:
        content, media_type = client.document_content(
            workspace_id,
            evidence["document_id"],
            evidence["document_version_id"],
        )
        st.download_button(
            "Download original source",
            data=content,
            file_name=evidence["document_title"],
            mime=media_type,
            icon=":material/download:",
        )
    except BackendAPIError as exc:
        st.error(str(exc), icon=":material/error:")


def _show_region_evidence(
    evidence: dict[str, Any], message_id: str, citation_index: int
) -> None:
    artifacts = {item["kind"]: item for item in evidence["artifacts"]}
    page_render = artifacts.get("page_render")
    crop = artifacts.get("region_crop")
    visual_tab, layers_tab, provenance_tab = st.tabs(
        ["Source location", "Evidence layers", "Provenance"]
    )
    with visual_tab:
        zoom = st.slider(
            "Page zoom",
            min_value=50,
            max_value=200,
            value=100,
            step=25,
            key=f"evidence_zoom_{message_id}_{citation_index}",
        )
        if page_render:
            page_bytes = _artifact_bytes(page_render, message_id, citation_index)
            if page_bytes is not None:
                highlighted = _highlight_region(page_bytes, evidence["region"])
                image = Image.open(BytesIO(highlighted))
                st.image(
                    highlighted,
                    caption="Full source page; the double outline marks the cited region.",
                    width=max(240, int(image.width * zoom / 100)),
                )
        else:
            st.info("A full-page render is not available for this evidence.")
        if crop:
            crop_bytes = _artifact_bytes(crop, message_id, citation_index)
            if crop_bytes is not None:
                st.image(crop_bytes, caption="Exact cited source crop", width="stretch")
    with layers_tab:
        text_layers = [
            item
            for item in evidence["artifacts"]
            if item["kind"]
            in {
                "ocr_text",
                "source_caption",
                "deterministic_caption",
                "generated_description",
            }
        ]
        if not text_layers:
            st.info("No additional text layers were produced for this region.")
        for artifact in text_layers:
            content = _artifact_bytes(artifact, message_id, citation_index)
            if content is None:
                continue
            st.markdown(f"**{artifact['kind'].replace('_', ' ').title()}**")
            st.caption(
                f"{artifact['provenance_class'].title()} · "
                f"{artifact['producer_name']} {artifact['producer_revision']}"
            )
            st.write(content.decode("utf-8", errors="replace"))
    with provenance_tab:
        region = evidence["region"]
        st.write(
            f"Extractor: `{region['extractor_name']} {region['extractor_revision']}`"
        )
        st.write(f"Locator contract: `{region['locator_schema_revision']}`")
        st.write(
            "Location: "
            f"x={region['bbox_x']:.4f}, y={region['bbox_y']:.4f}, "
            f"width={region['bbox_width']:.4f}, height={region['bbox_height']:.4f}"
        )
        for artifact in evidence["artifacts"]:
            st.caption(
                f"{artifact['kind'].replace('_', ' ').title()}: "
                f"{artifact['provenance_class']} · {artifact['validation_state']} · "
                f"{artifact['schema_revision']}"
            )


def _artifact_bytes(
    artifact: dict[str, Any], message_id: str, citation_index: int
) -> bytes | None:
    try:
        content, _ = client.evidence_artifact(
            workspace_id,
            selected_id,
            message_id,
            citation_index,
            artifact["id"],
        )
        return content
    except BackendAPIError as exc:
        st.error(str(exc), icon=":material/error:")
        return None


def _highlight_region(page_bytes: bytes, region: dict[str, Any]) -> bytes:
    image = Image.open(BytesIO(page_bytes)).convert("RGB")
    left = round(region["bbox_x"] * image.width)
    top = round(region["bbox_y"] * image.height)
    right = round((region["bbox_x"] + region["bbox_width"]) * image.width)
    bottom = round((region["bbox_y"] + region["bbox_height"]) * image.height)
    width = max(3, round(min(image.size) * 0.006))
    drawing = ImageDraw.Draw(image)
    drawing.rectangle((left, top, right, bottom), outline="white", width=width * 2)
    drawing.rectangle((left, top, right, bottom), outline="black", width=width)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _table_html(table: dict[str, Any]) -> str:
    cells_by_row: dict[int, list[dict[str, Any]]] = {}
    for cell in table["cells"]:
        cells_by_row.setdefault(cell["row_index"], []).append(cell)
    rows: list[str] = []
    for row_index in range(table["row_count"]):
        rendered: list[str] = []
        for cell in sorted(cells_by_row.get(row_index, []), key=lambda item: item["column_index"]):
            tag = "th" if cell["is_header"] else "td"
            marker = '<span class="mm-rag-cited">CITED</span> ' if cell["cited"] else ""
            rendered.append(
                f'<{tag} rowspan="{cell["row_span"]}" colspan="{cell["column_span"]}" '
                f'class="{"cited-cell" if cell["cited"] else ""}">'
                f"{marker}{escape(cell['text'])}</{tag}>"
            )
        rows.append(f"<tr>{''.join(rendered)}</tr>")
    return (
        "<style>"
        ".mm-rag-evidence-table{border-collapse:collapse;width:100%;font-size:.92rem}"
        ".mm-rag-evidence-table th,.mm-rag-evidence-table td{border:1px solid "
        "currentColor;padding:.45rem;text-align:left;vertical-align:top}"
        ".mm-rag-evidence-table .cited-cell{outline:3px double currentColor;"
        "outline-offset:-4px;font-weight:650}"
        ".mm-rag-cited{font-size:.65rem;border:1px solid currentColor;"
        "padding:.08rem .2rem;margin-right:.2rem}"
        "</style>"
        f'<div style="overflow-x:auto"><table class="mm-rag-evidence-table" '
        f'aria-label="Structured evidence table with {table["row_count"]} rows and '
        f'{table["column_count"]} columns">{"".join(rows)}</table></div>'
    )


def _display_value(value: str, unit: str | None, currency: str | None) -> str:
    if currency:
        return f"{currency} {value}"
    if unit == "%":
        return f"{value}%"
    return f"{value} {unit}" if unit else value


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
        st.caption(
            "Workspace searches every ready document you can access here; Collection "
            "searches one named group; Documents searches only the files you select."
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
            for citation_index, citation in enumerate(message["citations"]):
                display_index = citation_index + 1
                label = f"[{display_index}] {citation['document_title']}"
                if citation.get("page_number"):
                    label += f" · page {citation['page_number']}"
                with st.expander(label, icon=":material/article:"):
                    st.write(citation["excerpt"])
                    if st.button(
                        "Inspect evidence",
                        icon=":material/visibility:",
                        key=f"evidence_{message['id']}_{display_index}",
                    ):
                        show_evidence(citation, message["id"], citation_index)

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
