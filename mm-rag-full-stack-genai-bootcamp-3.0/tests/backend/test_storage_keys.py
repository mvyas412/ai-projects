from uuid import UUID

import pytest

from backend.app.storage.keys import (
    attempt_artifact_key,
    generation_artifact_key,
    original_object_key,
)

WORKSPACE_ID = UUID("00000000-0000-4000-8000-000000000001")
DOCUMENT_ID = UUID("00000000-0000-4000-8000-000000000002")
VERSION_ID = UUID("00000000-0000-4000-8000-000000000003")
JOB_ID = UUID("00000000-0000-4000-8000-000000000004")
ATTEMPT_ID = UUID("00000000-0000-4000-8000-000000000005")
GENERATION_ID = UUID("00000000-0000-4000-8000-000000000006")


def test_original_key_uses_only_trusted_opaque_identity() -> None:
    key = original_object_key(
        workspace_id=WORKSPACE_ID,
        document_id=DOCUMENT_ID,
        version_id=VERSION_ID,
    )

    assert key == (
        f"workspaces/{WORKSPACE_ID}/documents/{DOCUMENT_ID}/versions/{VERSION_ID}/original"
    )


def test_attempt_and_generation_keys_are_immutable_and_scoped() -> None:
    assert attempt_artifact_key(
        workspace_id=WORKSPACE_ID,
        job_id=JOB_ID,
        attempt_id=ATTEMPT_ID,
        artifact_name="chunks.jsonl",
    ) == (f"workspaces/{WORKSPACE_ID}/jobs/{JOB_ID}/attempts/{ATTEMPT_ID}/artifacts/chunks.jsonl")
    assert generation_artifact_key(
        workspace_id=WORKSPACE_ID,
        document_id=DOCUMENT_ID,
        version_id=VERSION_ID,
        generation_id=GENERATION_ID,
        artifact_name="manifest.json",
    ) == (
        f"workspaces/{WORKSPACE_ID}/documents/{DOCUMENT_ID}/versions/{VERSION_ID}/"
        f"generations/{GENERATION_ID}/artifacts/manifest.json"
    )


@pytest.mark.parametrize("name", ["../secret", "a/b", "Unsafe.JSON", ".hidden", "a..b"])
def test_artifact_keys_reject_untrusted_path_material(name: str) -> None:
    with pytest.raises(ValueError):
        attempt_artifact_key(
            workspace_id=WORKSPACE_ID,
            job_id=JOB_ID,
            attempt_id=ATTEMPT_ID,
            artifact_name=name,
        )
