import re
from uuid import UUID

_ARTIFACT_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,126}[a-z0-9]$|^[a-z0-9]$")


def original_object_key(*, workspace_id: UUID, document_id: UUID, version_id: UUID) -> str:
    return f"workspaces/{workspace_id}/documents/{document_id}/versions/{version_id}/original"


def attempt_artifact_key(
    *, workspace_id: UUID, job_id: UUID, attempt_id: UUID, artifact_name: str
) -> str:
    return (
        f"workspaces/{workspace_id}/jobs/{job_id}/attempts/{attempt_id}/"
        f"artifacts/{_validated_artifact_name(artifact_name)}"
    )


def generation_artifact_key(
    *,
    workspace_id: UUID,
    document_id: UUID,
    version_id: UUID,
    generation_id: UUID,
    artifact_name: str,
) -> str:
    return (
        f"workspaces/{workspace_id}/documents/{document_id}/versions/{version_id}/"
        f"generations/{generation_id}/artifacts/{_validated_artifact_name(artifact_name)}"
    )


def compliance_export_key(*, workspace_id: UUID, export_id: UUID) -> str:
    return (
        f"workspaces/{workspace_id}/compliance-exports/{export_id}/"
        "audit-events-v1.json"
    )


def _validated_artifact_name(value: str) -> str:
    if not _ARTIFACT_NAME.fullmatch(value) or ".." in value:
        raise ValueError("Artifact name must use a safe internal identifier")
    return value
