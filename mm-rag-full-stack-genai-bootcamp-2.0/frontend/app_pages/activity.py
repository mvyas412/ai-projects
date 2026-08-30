from datetime import datetime

import pandas as pd
import streamlit as st
from utils.api import BackendAPIError
from utils.runtime import api_client, selected_workspace

workspace_id, _ = selected_workspace()
st.caption("A workspace-scoped record of security-relevant product actions.")

try:
    events = api_client().activity(workspace_id)
except BackendAPIError as exc:
    st.error(str(exc), icon=":material/error:")
    st.stop()

if not events:
    st.info("Activity will appear as documents, collections, and conversations change.")
    st.stop()

labels = {
    "workspace.provisioned": "Workspace provisioned",
    "workspace.created": "Workspace created",
    "document.created": "Document uploaded",
    "document.version_created": "Document version added",
    "document.version_indexed": "Document indexed",
    "document.archived": "Document archived",
    "collection.created": "Collection created",
    "collection.document_added": "Document added to collection",
    "collection.document_removed": "Document removed from collection",
    "conversation.created": "Conversation started",
    "conversation.message_created": "Grounded answer created",
}
action_options = ["All", *sorted({labels.get(item["action"], item["action"]) for item in events})]
selected_action = st.selectbox("Filter by action", action_options)
filtered = [
    event
    for event in events
    if selected_action == "All"
    or labels.get(event["action"], event["action"]) == selected_action
]

rows = [
    {
        "When": datetime.fromisoformat(event["created_at"].replace("Z", "+00:00")),
        "Action": labels.get(event["action"], event["action"]),
        "Actor": event["actor_display_name"],
        "Resource": event["resource_type"].capitalize(),
        "Details": ", ".join(f"{key}: {value}" for key, value in event["details"].items()),
    }
    for event in filtered
]
st.dataframe(
    pd.DataFrame(rows),
    column_config={
        "When": st.column_config.DatetimeColumn(format="MMM DD, YYYY · h:mm a"),
        "Action": st.column_config.TextColumn(pinned=True),
    },
    hide_index=True,
    key="activity_table",
)
st.caption(f"Showing {len(filtered)} of {len(events)} most recent events.")
