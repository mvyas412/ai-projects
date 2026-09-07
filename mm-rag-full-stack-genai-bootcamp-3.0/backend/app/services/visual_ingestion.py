from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from backend.app.db.rls import DatabasePurpose, set_rls_context
from backend.app.db.session import SessionFactory
from backend.app.models.table import TableCell, TableColumn, TableRegion, TableValidationState
from backend.app.models.visual import (
    ArtifactKind,
    ArtifactValidationState,
    ContentArtifact,
    ContentRegion,
)
from backend.app.storage.base import ObjectIntegrityError, ObjectStorage
from backend.app.storage.keys import attempt_artifact_key, generation_artifact_key
from backend.app.tables.normalization import (
    TABLE_SCHEMA_REVISION,
    NormalizedTable,
    TableNormalizationError,
    normalize_table,
    normalized_table_csv,
    normalized_table_json,
    table_cell_id,
    table_column_id,
)
from backend.app.visual.extraction import DocumentStructureExtractor, ExtractedRegion
from backend.app.visual.indexing import (
    VisualIndexingRequest,
    VisualRegionIndexer,
    VisualRegionIndexItem,
)
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
    document_title: str
    media_type: str
    content: bytes


@dataclass(frozen=True, slots=True)
class VisualProcessingResult:
    region_count: int
    artifact_count: int
    artifact_bytes: int
    manifest_sha256: str
    vector_count: int = 0
    vector_profile: str | None = None
    vector_profile_fingerprint: str | None = None
    table_count: int = 0
    exact_table_count: int = 0
    table_cell_count: int = 0


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
    schema_revision: str = ARTIFACT_SCHEMA_REVISION
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
        visual_indexer: VisualRegionIndexer | None = None,
        table_exact_max_rows: int = 1000,
        table_max_columns: int = 100,
    ) -> None:
        self._session_factory = session_factory
        self._storage = artifact_storage
        self._extractor = extractor
        self._extractor_config_sha256 = extractor_config_sha256(extractor_config)
        self._visual_indexer = visual_indexer
        self._table_exact_max_rows = table_exact_max_rows
        self._table_max_columns = table_max_columns

    def process(self, request: VisualProcessingRequest) -> VisualProcessingResult:
        extracted = self._extractor.extract(request.content, request.media_type)
        region_rows: list[ContentRegion] = []
        artifact_rows: list[ContentArtifact] = []
        table_rows: list[TableRegion] = []
        table_column_rows: list[TableColumn] = []
        table_cell_rows: list[TableCell] = []
        index_items: list[VisualRegionIndexItem] = []
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
            try:
                normalized_table = (
                    normalize_table(
                        region.table,
                        generation_id=request.generation_id,
                        region_id=region_id,
                        max_exact_rows=self._table_exact_max_rows,
                        max_columns=self._table_max_columns,
                        confidence=region.confidence,
                    )
                    if region.table is not None
                    else None
                )
            except TableNormalizationError:
                # Keep visual/text evidence when exact table structure is unusable.
                normalized_table = None
            drafts = self._artifact_drafts(
                region,
                extracted.extractor_name,
                extracted.extractor_revision,
                normalized_table,
            )
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
                        schema_revision=draft.schema_revision,
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
            if normalized_table is not None:
                table_row, columns, cells = self._table_rows(
                    request=request,
                    region=region,
                    normalized=normalized_table,
                    extractor_name=extracted.extractor_name,
                    extractor_revision=extracted.extractor_revision,
                    source_crop_artifact_id=parent_ids[ArtifactKind.REGION_CROP],
                    normalized_artifact_id=parent_ids[ArtifactKind.NORMALIZED_JSON],
                )
                table_rows.append(table_row)
                table_column_rows.extend(columns)
                table_cell_rows.extend(cells)
            manifest_regions.append(
                {
                    "artifacts": sorted(region_artifacts, key=lambda item: str(item["kind"])),
                    "locator_sha256": locator.sha256,
                    "region_id": str(region_id),
                    "table_id": (
                        str(normalized_table.table_id) if normalized_table is not None else None
                    ),
                }
            )
            index_items.append(
                VisualRegionIndexItem(
                    region_id=region_id,
                    page_number=region.page_number,
                    region_kind=region.kind.value,
                    image=region.crop,
                    content=_region_search_text(region),
                )
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
            session.add_all(table_rows)
            session.flush()
            session.add_all(table_column_rows)
            session.add_all(table_cell_rows)
            session.flush()
        indexing_result = (
            self._visual_indexer.index(
                VisualIndexingRequest(
                    workspace_id=request.workspace_id,
                    document_id=request.document_id,
                    document_version_id=request.document_version_id,
                    generation_id=request.generation_id,
                    document_title=request.document_title,
                    regions=tuple(index_items),
                )
            )
            if self._visual_indexer is not None
            else None
        )
        manifest_sha256 = canonical_manifest_sha256(
            {"regions": sorted(manifest_regions, key=lambda item: str(item["region_id"]))}
        )
        return VisualProcessingResult(
            region_count=len(region_rows),
            artifact_count=len(artifact_rows),
            artifact_bytes=artifact_bytes,
            manifest_sha256=manifest_sha256,
            vector_count=indexing_result.vector_count if indexing_result else 0,
            vector_profile=indexing_result.profile if indexing_result else None,
            vector_profile_fingerprint=(
                indexing_result.profile_fingerprint if indexing_result else None
            ),
            table_count=len(table_rows),
            exact_table_count=sum(
                row.validation_state == TableValidationState.VALIDATED.value
                for row in table_rows
            ),
            table_cell_count=len(table_cell_rows),
        )

    @staticmethod
    def _artifact_drafts(
        region: ExtractedRegion,
        producer_name: str,
        producer_revision: str,
        normalized_table: NormalizedTable | None,
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
                {
                    "columns": region.table.columns,
                    "rows": region.table.rows,
                    "cells": [
                        {
                            "row_index": cell.row_index,
                            "column_index": cell.column_index,
                            "row_span": cell.row_span,
                            "column_span": cell.column_span,
                            "text": cell.text,
                            "column_header": cell.column_header,
                            "row_header": cell.row_header,
                        }
                        for cell in region.table.cells
                    ],
                },
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
        if normalized_table is not None:
            drafts.extend(
                (
                    _ArtifactDraft(
                        ArtifactKind.NORMALIZED_JSON,
                        normalized_table_json(normalized_table),
                        "application/json",
                        "mm-rag",
                        "table-normalizer-v1",
                        schema_revision=TABLE_SCHEMA_REVISION,
                    ),
                    _ArtifactDraft(
                        ArtifactKind.NORMALIZED_CSV,
                        normalized_table_csv(normalized_table),
                        "text/csv; charset=utf-8",
                        "mm-rag",
                        "table-normalizer-v1",
                        schema_revision=TABLE_SCHEMA_REVISION,
                    ),
                )
            )
        return tuple(drafts)

    @staticmethod
    def _table_rows(
        *,
        request: VisualProcessingRequest,
        region: ExtractedRegion,
        normalized: NormalizedTable,
        extractor_name: str,
        extractor_revision: str,
        source_crop_artifact_id: UUID,
        normalized_artifact_id: UUID,
    ) -> tuple[TableRegion, list[TableColumn], list[TableCell]]:
        common = {
            "workspace_id": request.workspace_id,
            "document_id": request.document_id,
            "document_version_id": request.document_version_id,
            "generation_id": request.generation_id,
            "creation_attempt_id": request.attempt_id,
            "table_id": normalized.table_id,
        }
        table_row = TableRegion(
            id=normalized.table_id,
            workspace_id=request.workspace_id,
            document_id=request.document_id,
            document_version_id=request.document_version_id,
            generation_id=request.generation_id,
            region_id=normalized.region_id,
            creation_attempt_id=request.attempt_id,
            source_crop_artifact_id=source_crop_artifact_id,
            normalized_artifact_id=normalized_artifact_id,
            page_number=region.page_number,
            header_row_count=normalized.header_row_count,
            row_count=normalized.row_count,
            column_count=normalized.column_count,
            structure_schema_revision="normalized-table-v1",
            structure_sha256=normalized.structure_sha256,
            extractor_name=extractor_name,
            extractor_revision=extractor_revision,
            validation_state=normalized.validation_state.value,
            validation_codes=list(normalized.validation_codes),
            confidence=region.confidence,
        )
        columns = [
            TableColumn(
                id=table_column_id(normalized.table_id, column.index),
                **common,
                column_index=column.index,
                raw_header=column.raw_header,
                normalized_header=column.normalized_header,
                logical_type=column.logical_type.value,
                unit=column.unit,
                currency=column.currency,
            )
            for column in normalized.columns
        ]
        cells = [
            TableCell(
                id=table_cell_id(normalized.table_id, cell.row_index, cell.column_index),
                **common,
                row_index=cell.row_index,
                column_index=cell.column_index,
                row_span=cell.row_span,
                column_span=cell.column_span,
                is_header=cell.is_header,
                header_associations=[
                    str(table_cell_id(normalized.table_id, row, column))
                    for row, column in cell.header_positions
                ],
                raw_text=cell.raw_text,
                normalized_text=cell.normalized_text,
                logical_type=cell.logical_type.value,
                normalized_value=cell.normalized_value,
                unit=cell.unit,
                currency=cell.currency,
                bbox_x=cell.bbox.x if cell.bbox else None,
                bbox_y=cell.bbox.y if cell.bbox else None,
                bbox_width=cell.bbox.width if cell.bbox else None,
                bbox_height=cell.bbox.height if cell.bbox else None,
                confidence=region.confidence,
            )
            for cell in normalized.cells
        ]
        return table_row, columns, cells

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
            schema_revision=draft.schema_revision,
            prompt_revision=draft.prompt_revision,
            confidence=None,
            validation_state=ArtifactValidationState.VALIDATED.value,
        )


def _deterministic_caption(region: ExtractedRegion) -> str:
    label = region.kind.value.replace("_", " ")
    source = f" Source caption: {region.source_caption}" if region.source_caption else ""
    return f"{label.capitalize()} on page {region.page_number}.{source}".strip()


def _region_search_text(region: ExtractedRegion) -> str:
    parts = [_deterministic_caption(region)]
    if region.ocr_text:
        parts.append(f"Extracted text: {region.ocr_text}")
    return "\n".join(parts)[:2000]


def _extension(media_type: str) -> str:
    if media_type.startswith("image/png"):
        return "png"
    if media_type == "application/json":
        return "json"
    if media_type.startswith("text/csv"):
        return "csv"
    return "txt"
