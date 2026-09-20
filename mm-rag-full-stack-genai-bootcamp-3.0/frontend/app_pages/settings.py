from datetime import UTC, datetime, timedelta

import streamlit as st
from utils.api import BackendAPIError
from utils.runtime import api_client, current_user_identity, selected_workspace

_, workspace = selected_workspace()
display_name, email = current_user_identity()
st.caption("Review your session, workspace access, and service readiness.")

identity, access = st.columns(2, gap="large")
with identity.container(border=True, height="stretch"):
    st.subheader("Account")
    st.write(display_name)
    st.caption(email or "Email not provided by the identity provider")
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

if workspace["role"] in {"owner", "admin"}:
    st.subheader("Monthly retention review")
    st.caption(
        "Preview eligible records without deleting anything. Applying retention remains "
        "disabled until a separate policy decision and fresh authorization."
    )
    try:
        recent_activity = api_client().activity(str(workspace["id"]), limit=200)
        prior_previews = [
            item for item in recent_activity if item["action"] == "retention.preview_generated"
        ]
        latest_preview = max(
            (
                datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
                for item in prior_previews
            ),
            default=None,
        )
        if latest_preview is None or datetime.now(UTC) - latest_preview > timedelta(days=31):
            st.warning("The monthly retention preview is due. No deletion will be applied.")
        else:
            st.info(f"Latest preview: {latest_preview.date().isoformat()} · apply remains disabled")
    except BackendAPIError as exc:
        st.error(str(exc), icon=":material/error:")
    if st.button("Generate preview", icon=":material/preview:"):
        try:
            preview = api_client().retention_preview(str(workspace["id"]))
            counts = {
                "Documents": preview["due_document_deletions"],
                "Conversations": preview["due_conversation_deletions"],
                "Inactive generations": preview["inactive_generations"],
                "Terminal jobs": preview["terminal_jobs"],
                "Audit events": preview["security_audit_events"],
                "Orphan objects": preview["orphan_objects"],
            }
            st.success("Preview generated. No records were deleted.")
            st.caption(
                f"Policy {preview['policy_revision']} · generated {preview['generated_at']}"
            )
            st.dataframe(
                [{"Category": name, "Eligible": count} for name, count in counts.items()],
                hide_index=True,
                use_container_width=True,
            )
            # The one-time preview token is intentionally neither displayed nor persisted.
        except BackendAPIError as exc:
            st.error(str(exc), icon=":material/error:")

    st.subheader("Feedback review")
    st.caption(
        "Workspace feedback stays tenant-scoped. Promotion records a reviewed regression-case "
        "identifier; it does not train or tune the model automatically."
    )
    try:
        feedback_rows = api_client().feedback(str(workspace["id"]))
    except BackendAPIError as exc:
        st.error(str(exc), icon=":material/error:")
        feedback_rows = []
    pending = [item for item in feedback_rows if item["review_status"] == "pending"]
    if not pending:
        st.info("No feedback is awaiting review.")
    for item in pending:
        label = f"{item['reason'].replace('_', ' ').title()} · rating {item['rating']:+d}"
        with st.expander(label, icon=":material/feedback:"):
            if item.get("comment"):
                st.write(item["comment"])
            st.caption(
                f"Submitted {item['created_at']} · retained until {item['retention_expires_at']}"
            )
            decision = st.selectbox(
                "Review decision",
                ["reviewed", "dismissed", "promoted"],
                key=f"feedback_review_{item['id']}",
            )
            case_id = st.text_input(
                "Regression case ID",
                disabled=decision != "promoted",
                placeholder="customer-safe-regression-001",
                key=f"feedback_case_{item['id']}",
            )
            if st.button("Record review", key=f"feedback_submit_{item['id']}"):
                try:
                    api_client().review_feedback(
                        str(workspace["id"]),
                        item["id"],
                        status=decision,
                        promoted_case_id=case_id or None,
                    )
                    st.toast("Feedback review recorded", icon=":material/check:")
                    st.rerun()
                except BackendAPIError as exc:
                    st.error(str(exc), icon=":material/error:")
