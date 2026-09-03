from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from backend.app.db.rls import DatabasePurpose, set_rls_context
from backend.app.db.session import SessionFactory
from backend.app.models.visual import (
    ArtifactKind,
    ArtifactValidationState,
    ContentArtifact,
    ContentRegion,
)
from backend.app.storage.base import ObjectIntegrityError, ObjectStorage
from backend.app.storage.keys import attempt_artifact_key, generation_artifact_key
from backend.app.visual.extraction import DocumentStructureExtractor, ExtractedRegion
from backend.app.visual.provenance import (
    ARTIFACT_SCHEMA_REVISION,
    LOCATOR_SCHEMA_REVISION,
    ArtifactIdentity,
    RegionLocator,
    canonical_manifest_sha256,
    content_sha256,
    extractor_config_sha256,
)


@dataclass(frozen=True, slots=True)
class VisualProcessingRequest:
    workspace_id: UUID
    document_id: UUID
    document_version_id: UUID
    generation_id: UUID
    job_id: UUID
    attempt_id: UUID
    media_type: str
    content: bytes


@dataclass(frozen=True, slots=True)
class VisualProcessingResult:
    region_count: int
    artifact_count: int
    artifact_bytes: int
    manifest_sha256: str


class VisualIngestionProcessor(Protocol):
    def process(self, request: VisualProcessingRequest) -> VisualProcessingResult: ...


class NoopVisualIngestionProcessor:
    def process(self, request: VisualProcessingRequest) -> VisualProcessingResult:
        return VisualProcessingResult(0, 0, 0, canonical_manifest_sha256({"regions": []}))


@dataclass(frozen=True, slots=True)
class _ArtifactDraft:
    kind: ArtifactKind
    content: bytes
    media_type: str
    producer_name: str
    producer_revision: str
    parent_artifact_id: UUID | None = None
    prompt_revision: str | None = None
    pixel_width: int | None = None
    pixel_height: int | None = None


class LocalVisualIngestionProcessor:
    """Persist an inactive immutable artifact set before generation promotion."""

    def __init__(
        self,
        session_factory: SessionFactory,
        artifact_storage: ObjectStorage,
        extractor: DocumentStructureExtractor,
        *,
        extractor_config: dict[str, object],
    ) -> None:
        self._session_factory = session_factory
        self._storage = artifact_storage
        self._extractor = extractor
        self._extractor_config_sha256 = extractor_config_sha256(extractor_config)

    def process(self, request: VisualProcessingRequest) -> VisualProcessingResult:
        extracted = self._extractor.extract(request.content, request.media_type)
        region_rows: list[ContentRegion] = []
        artifact_rows: list[ContentArtifact] = []
        manifest_regions: list[dict[str, object]] = []
        artifact_bytes = 0
        for region in extracted.regions:
            locator = RegionLocator(
                page_number=region.page_number,
                page_render_sha256=region.page_render_sha256,
                kind=region.kind,
                bbox=region.bbox,
                page_width=region.page_width,
                page_height=region.page_height,
                rotation=region.rotation,
                extractor_name=extracted.extractor_name,
                extractor_revision=extracted.extractor_revision,
                extractor_config_sha256=self._extractor_config_sha256,
                ordinal=region.ordinal,
            )
            region_id = locator.stable_id(request.generation_id)
            region_rows.append(
                ContentRegion(
                    id=region_id,
                    workspace_id=request.workspace_id,
                    document_id=request.document_id,
                    document_version_id=request.document_version_id,
                    generation_id=request.generation_id,
                    creation_attempt_id=request.attempt_id,
                    page_number=region.page_number,
                    kind=region.kind.value,
                    ordinal=region.ordinal,
                    bbox_x=region.bbox.x,
                    bbox_y=region.bbox.y,
                    bbox_width=region.bbox.width,
                    bbox_height=region.bbox.height,
                    page_width=region.page_width,
                    page_height=region.page_height,
                    rotation=region.rotation,
                    locator_schema_revision=LOCATOR_SCHEMA_REVISION,
                    locator_sha256=locator.sha256,
                    page_render_sha256=region.page_render_sha256,
                    extractor_name=extracted.extractor_name,
                    extractor_revision=extracted.extractor_revision,
                    extractor_config_sha256=self._extractor_config_sha256,
                    source_caption=region.source_caption,
                    ocr_text=region.ocr_text,
                    confidence=region.confidence,
                )
            )
            drafts = self._artifact_drafts(region, extracted.extractor_name, extracted.extractor_revision)
            region_artifacts: list[dict[str, object]] = []
            parent_ids: dict[ArtifactKind, UUID] = {}
            for draft in drafts:
                parent_id = draft.parent_artifact_id
                if parent_id is None and draft.kind not in {ArtifactKind.PAGE_RENDER}:
                    parent_id = parent_ids.get(ArtifactKind.REGION_CROP)
                row = self._persist_artifact(
                    request=request,
                    region_id=region_id,
                    draft=_ArtifactDraft(
                        kind=draft.kind,
                        content=draft.content,
                        media_type=draft.media_type,
                        producer_name=draft.producer_name,
                        producer_revision=draft.producer_revision,
                        parent_artifact_id=parent_id,
                        prompt_revision=draft.prompt_revision,
                        pixel_width=draft.pixel_width,
                        pixel_height=draft.pixel_height,
                    ),
                )
                parent_ids[draft.kind] = row.id
                artifact_rows.append(row)
                artifact_bytes += row.byte_size
                region_artifacts.append(
                    {
                        "artifact_id": str(row.id),
                        "content_sha256": row.content_sha256,
                        "kind": row.kind,
                    }
                )
            manifest_regions.append(
                {
                    "artifacts": sorted(region_artifacts, key=lambda item: str(item["kind"])),
                    "locator_sha256": locator.sha256,
                    "region_id": str(region_id),
                }
            )

        with self._session_factory.begin() as session:
            set_rls_context(
                session,
                purpose=DatabasePurpose.WORKER,
                workspace_id=request.workspace_id,
                job_id=request.job_id,
            )
            session.add_all(region_rows)
            session.flush()
            session.add_all(artifact_rows)
            session.flush()
        manifest_sha256 = canonical_manifest_sha256(
            {"regions": sorted(manifest_regions, key=lambda item: str(item["region_id"]))}
        )
        return VisualProcessingResult(
            region_count=len(region_rows),
            artifact_count=len(artifact_rows),
            artifact_bytes=artifact_bytes,
            manifest_sha256=manifest_sha256,
        )

    @staticmethod
    def _artifact_drafts(
        region: ExtractedRegion, producer_name: str, producer_revision: str
    ) -> tuple[_ArtifactDraft, ...]:
        from io import BytesIO

        from PIL import Image

        page = Image.open(BytesIO(region.page_render))
        crop = Image.open(BytesIO(region.crop))
        drafts = [
            _ArtifactDraft(
                ArtifactKind.PAGE_RENDER,
                region.page_render,
                "image/png",
                producer_name,
                producer_revision,
                pixel_width=page.width,
                pixel_height=page.height,
            ),
            _ArtifactDraft(
                ArtifactKind.REGION_CROP,
                region.crop,
                "image/png",
                producer_name,
                producer_revision,
                pixel_width=crop.width,
                pixel_height=crop.height,
            ),
        ]
        if region.ocr_text:
            drafts.append(
                _ArtifactDraft(
                    ArtifactKind.OCR_TEXT,
                    region.ocr_text.encode("utf-8"),
                    "text/plain; charset=utf-8",
                    producer_name,
                    producer_revision,
                )
            )
        if region.source_caption:
            drafts.append(
                _ArtifactDraft(
                    ArtifactKind.SOURCE_CAPTION,
                    region.source_caption.encode("utf-8"),
                    "text/plain; charset=utf-8",
                    producer_name,
                    producer_revision,
                )
            )
        deterministic = _deterministic_caption(region).encode("utf-8")
        drafts.append(
            _ArtifactDraft(
                ArtifactKind.DETERMINISTIC_CAPTION,
                deterministic,
                "text/plain; charset=utf-8",
                "mm-rag",
                "deterministic-caption-v1",
            )
        )
        if region.table is not None:
            payload = json.dumps(
                {"columns": region.table.columns, "rows": region.table.rows},
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            drafts.append(
                _ArtifactDraft(
                    ArtifactKind.STRUCTURED_TABLE,
                    payload,
                    "application/json",
                    producer_name,
                    producer_revision,
                )
            )
        return tuple(drafts)

    def _persist_artifact(
        self,
        *,
        request: VisualProcessingRequest,
        region_id: UUID,
        draft: _ArtifactDraft,
    ) -> ContentArtifact:
        checksum = content_sha256(draft.content)
        identity = ArtifactIdentity(
            region_id=region_id,
            kind=draft.kind.value,
            content_sha256=checksum,
            producer_name=draft.producer_name,
            producer_revision=draft.producer_revision,
            prompt_revision=draft.prompt_revision,
        )
        artifact_id = identity.stable_id(request.generation_id)
        extension = _extension(draft.media_type)
        artifact_name = f"region-{region_id}-{draft.kind.value}.{extension}"
        attempt_key = attempt_artifact_key(
            workspace_id=request.workspace_id,
            job_id=request.job_id,
            attempt_id=request.attempt_id,
            artifact_name=artifact_name,
        )
        final_key = generation_artifact_key(
            workspace_id=request.workspace_id,
            document_id=request.document_id,
            version_id=request.document_version_id,
            generation_id=request.generation_id,
            artifact_name=artifact_name,
        )
        metadata = {
            "workspace-id": str(request.workspace_id),
            "generation-id": str(request.generation_id),
            "region-id": str(region_id),
            "artifact-id": str(artifact_id),
        }
        self._storage.put(
            attempt_key, draft.content, media_type=draft.media_type, metadata=metadata
        )
        stored = self._storage.put(
            final_key, draft.content, media_type=draft.media_type, metadata=metadata
        )
        if stored.content_sha256 != checksum or stored.byte_size != len(draft.content):
            raise ObjectIntegrityError("Visual artifact identity mismatch")
        return ContentArtifact(
            id=artifact_id,
            workspace_id=request.workspace_id,
            document_id=request.document_id,
            document_version_id=request.document_version_id,
            generation_id=request.generation_id,
            region_id=region_id,
            parent_artifact_id=draft.parent_artifact_id,
            creation_attempt_id=request.attempt_id,
            kind=draft.kind.value,
            object_key=final_key,
            media_type=draft.media_type,
            byte_size=len(draft.content),
            content_sha256=checksum,
            pixel_width=draft.pixel_width,
            pixel_height=draft.pixel_height,
            producer_name=draft.producer_name,
            producer_revision=draft.producer_revision,
            schema_revision=ARTIFACT_SCHEMA_REVISION,
            prompt_revision=draft.prompt_revision,
            confidence=None,
            validation_state=ArtifactValidationState.VALIDATED.value,
        )


def _deterministic_caption(region: ExtractedRegion) -> str:
    label = region.kind.value.replace("_", " ")
    source = f" Source caption: {region.source_caption}" if region.source_caption else ""
    return f"{label.capitalize()} on page {region.page_number}.{source}".strip()


def _extension(media_type: str) -> str:
    if media_type.startswith("image/png"):
        return "png"
    if media_type == "application/json":
        return "json"
    return "txt"
