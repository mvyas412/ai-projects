from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import (
    ArtifactKind,
    ArtifactValidationState,
    CalculationTrace,
    ContentArtifact,
    ContentRegion,
    ConversationMessage,
    Document,
    DocumentVersion,
    MessageRole,
    TableCell,
    TableColumn,
    TableRegion,
    TableValidationState,
    User,
)
from backend.app.repositories.conversations import ConversationRepository
from backend.app.repositories.documents import DocumentRepository
from backend.app.schemas.conversations import Citation
from backend.app.schemas.evidence import (
    EvidenceArtifactDescriptor,
    EvidenceCalculationDescriptor,
    EvidenceCalculationOperand,
    EvidenceDescriptor,
    EvidenceRegionDescriptor,
    EvidenceTableCell,
    EvidenceTableColumn,
    EvidenceTableDescriptor,
)
from backend.app.services.policy import (
    PolicyAction,
    PolicyDeniedError,
    PolicyNotFoundError,
    PolicyService,
    resource_context,
)
from backend.app.storage.base import ObjectStorage, ObjectStorageError


class EvidenceError(Exception):
    """Base class for safe, non-disclosing evidence failures."""


class EvidenceNotFoundError(EvidenceError):
    pass


class EvidenceIntegrityError(EvidenceError):
    pass


@dataclass(frozen=True, slots=True)
class EvidenceArtifactContent:
    content: bytes
    media_type: str
    filename: str


@dataclass(frozen=True, slots=True)
class _ResolvedEvidence:
    citation: Citation
    document: Document
    version: DocumentVersion
    region: ContentRegion | None
    artifacts: tuple[ContentArtifact, ...]
    table: TableRegion | None
    columns: tuple[TableColumn, ...]
    cells: tuple[TableCell, ...]
    trace: CalculationTrace | None


class EvidenceService:
    """Resolve persisted citation labels into current, authorized source evidence."""

    def __init__(self, session: Session, storage: ObjectStorage) -> None:
        self._session = session
        self._storage = storage
        self._conversations = ConversationRepository(session)
        self._documents = DocumentRepository(session)
        self._policy = PolicyService(session)

    def describe(
        self,
        *,
        user: User,
        workspace_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        citation_index: int,
    ) -> EvidenceDescriptor:
        resolved = self._resolve(
            user=user,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            citation_index=citation_index,
        )
        cited_cell_ids = self._cited_cell_ids(resolved)
        return EvidenceDescriptor(
            citation_index=citation_index,
            evidence_kind=resolved.citation.evidence_kind,
            document_id=resolved.document.id,
            document_version_id=resolved.version.id,
            generation_id=(
                resolved.citation.generation_id
                or resolved.version.active_generation_id
            ),
            document_title=resolved.document.title,
            page_number=resolved.citation.page_number,
            excerpt=resolved.citation.excerpt,
            region=(
                EvidenceRegionDescriptor(
                    id=resolved.region.id,
                    kind=resolved.region.kind,
                    page_number=resolved.region.page_number,
                    bbox_x=resolved.region.bbox_x,
                    bbox_y=resolved.region.bbox_y,
                    bbox_width=resolved.region.bbox_width,
                    bbox_height=resolved.region.bbox_height,
                    page_width=resolved.region.page_width,
                    page_height=resolved.region.page_height,
                    rotation=resolved.region.rotation,
                    extractor_name=resolved.region.extractor_name,
                    extractor_revision=resolved.region.extractor_revision,
                    locator_schema_revision=resolved.region.locator_schema_revision,
                    confidence=resolved.region.confidence,
                )
                if resolved.region is not None
                else None
            ),
            artifacts=[self._artifact_descriptor(item) for item in resolved.artifacts],
            table=self._table_descriptor(resolved, cited_cell_ids),
            calculation=self._calculation_descriptor(resolved),
        )

    def artifact_content(
        self,
        *,
        user: User,
        workspace_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        citation_index: int,
        artifact_id: UUID,
    ) -> EvidenceArtifactContent:
        resolved = self._resolve(
            user=user,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            citation_index=citation_index,
        )
        artifact = next((item for item in resolved.artifacts if item.id == artifact_id), None)
        if artifact is None:
            raise EvidenceNotFoundError
        try:
            stored = self._storage.head(artifact.object_key)
            if (
                stored.byte_size != artifact.byte_size
                or stored.media_type != artifact.media_type
                or not hmac.compare_digest(stored.content_sha256, artifact.content_sha256)
            ):
                raise EvidenceIntegrityError
            content = self._storage.read(artifact.object_key)
        except EvidenceIntegrityError:
            raise
        except ObjectStorageError as exc:
            raise EvidenceIntegrityError from exc
        if (
            len(content) != artifact.byte_size
            or not hmac.compare_digest(
                hashlib.sha256(content).hexdigest(), artifact.content_sha256
            )
        ):
            raise EvidenceIntegrityError
        return EvidenceArtifactContent(
            content=content,
            media_type=artifact.media_type,
            filename=f"evidence-{artifact.kind}.{_extension(artifact.media_type)}",
        )

    def _resolve(
        self,
        *,
        user: User,
        workspace_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        citation_index: int,
    ) -> _ResolvedEvidence:
        conversation = self._conversations.get(workspace_id, conversation_id)
        if conversation is None:
            raise EvidenceNotFoundError
        self._require(
            user,
            workspace_id,
            PolicyAction.CONVERSATION_READ,
            resource_context(conversation),
        )
        message = self._session.scalar(
            select(ConversationMessage).where(
                ConversationMessage.id == message_id,
                ConversationMessage.workspace_id == workspace_id,
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.role == MessageRole.ASSISTANT.value,
            )
        )
        if message is None or citation_index < 0 or citation_index >= len(message.citations):
            raise EvidenceNotFoundError
        try:
            citation = Citation.model_validate(message.citations[citation_index])
        except ValidationError as exc:
            raise EvidenceNotFoundError from exc

        document = self._documents.get_document(workspace_id, citation.document_id)
        if document is None:
            raise EvidenceNotFoundError
        self._require(
            user,
            workspace_id,
            PolicyAction.DOCUMENT_READ,
            resource_context(document),
        )
        version = self._documents.get_version(
            workspace_id, citation.document_id, citation.document_version_id
        )
        if version is None or version.active_generation_id is None:
            raise EvidenceNotFoundError
        if (
            citation.generation_id is None
            and citation.evidence_kind != "text"
        ) or (
            citation.generation_id is not None
            and version.active_generation_id != citation.generation_id
        ):
            raise EvidenceNotFoundError

        region = self._region(citation, workspace_id)
        artifacts = self._artifacts(citation, workspace_id, region)
        table, columns, cells = self._table(citation, workspace_id, region)
        trace = self._trace(citation, workspace_id, table)
        self._validate_cited_cells(citation, cells, trace)
        return _ResolvedEvidence(
            citation,
            document,
            version,
            region,
            artifacts,
            table,
            columns,
            cells,
            trace,
        )

    def _region(self, citation: Citation, workspace_id: UUID) -> ContentRegion | None:
        if citation.region_id is None:
            if citation.evidence_kind != "text":
                raise EvidenceNotFoundError
            return None
        if citation.generation_id is None:
            raise EvidenceNotFoundError
        region = self._session.scalar(
            select(ContentRegion).where(
                ContentRegion.id == citation.region_id,
                ContentRegion.workspace_id == workspace_id,
                ContentRegion.document_id == citation.document_id,
                ContentRegion.document_version_id == citation.document_version_id,
                ContentRegion.generation_id == citation.generation_id,
            )
        )
        expected_kind = (
            "image"
            if region is not None and region.kind == "photo"
            else "figure"
            if region is not None and region.kind == "other"
            else region.kind
            if region is not None
            else None
        )
        if (
            region is None
            or citation.page_number != region.page_number
            or citation.evidence_kind not in {expected_kind, "calculation"}
        ):
            raise EvidenceNotFoundError
        return region

    def _artifacts(
        self,
        citation: Citation,
        workspace_id: UUID,
        region: ContentRegion | None,
    ) -> tuple[ContentArtifact, ...]:
        if region is None:
            return ()
        return tuple(
            self._session.scalars(
                select(ContentArtifact)
                .where(
                    ContentArtifact.workspace_id == workspace_id,
                    ContentArtifact.document_id == citation.document_id,
                    ContentArtifact.document_version_id == citation.document_version_id,
                    ContentArtifact.generation_id == citation.generation_id,
                    ContentArtifact.region_id == region.id,
                    ContentArtifact.validation_state
                    != ArtifactValidationState.REJECTED.value,
                )
                .order_by(ContentArtifact.kind, ContentArtifact.id)
            )
        )

    def _table(
        self,
        citation: Citation,
        workspace_id: UUID,
        region: ContentRegion | None,
    ) -> tuple[TableRegion | None, tuple[TableColumn, ...], tuple[TableCell, ...]]:
        if region is None or citation.evidence_kind not in {"table", "calculation"}:
            if citation.table_id is not None or citation.cell_ids:
                raise EvidenceNotFoundError
            return None, (), ()
        table = self._session.scalar(
            select(TableRegion).where(
                TableRegion.workspace_id == workspace_id,
                TableRegion.document_id == citation.document_id,
                TableRegion.document_version_id == citation.document_version_id,
                TableRegion.generation_id == citation.generation_id,
                TableRegion.region_id == region.id,
                TableRegion.validation_state != TableValidationState.REJECTED.value,
            )
        )
        if table is None or (citation.table_id is not None and citation.table_id != table.id):
            raise EvidenceNotFoundError
        columns = tuple(
            self._session.scalars(
                select(TableColumn)
                .where(
                    TableColumn.workspace_id == workspace_id,
                    TableColumn.generation_id == citation.generation_id,
                    TableColumn.table_id == table.id,
                )
                .order_by(TableColumn.column_index)
            )
        )
        cells = tuple(
            self._session.scalars(
                select(TableCell)
                .where(
                    TableCell.workspace_id == workspace_id,
                    TableCell.generation_id == citation.generation_id,
                    TableCell.table_id == table.id,
                )
                .order_by(TableCell.row_index, TableCell.column_index)
            )
        )
        if len(columns) != table.column_count or not cells:
            raise EvidenceNotFoundError
        return table, columns, cells

    def _trace(
        self,
        citation: Citation,
        workspace_id: UUID,
        table: TableRegion | None,
    ) -> CalculationTrace | None:
        if citation.evidence_kind != "calculation":
            if citation.calculation_trace_id is not None:
                raise EvidenceNotFoundError
            return None
        if table is None or citation.calculation_trace_id is None:
            raise EvidenceNotFoundError
        trace = self._session.scalar(
            select(CalculationTrace).where(
                CalculationTrace.id == citation.calculation_trace_id,
                CalculationTrace.workspace_id == workspace_id,
                CalculationTrace.document_id == citation.document_id,
                CalculationTrace.document_version_id == citation.document_version_id,
                CalculationTrace.generation_id == citation.generation_id,
                CalculationTrace.region_id == citation.region_id,
                CalculationTrace.table_id == table.id,
            )
        )
        if trace is None or table.validation_state != TableValidationState.VALIDATED.value:
            raise EvidenceNotFoundError
        return trace

    @staticmethod
    def _validate_cited_cells(
        citation: Citation,
        cells: tuple[TableCell, ...],
        trace: CalculationTrace | None,
    ) -> None:
        available = {cell.id for cell in cells}
        if any(cell_id not in available for cell_id in citation.cell_ids):
            raise EvidenceNotFoundError
        if trace is not None and [str(item) for item in citation.cell_ids] != trace.cell_ids:
            raise EvidenceNotFoundError

    @staticmethod
    def _cited_cell_ids(resolved: _ResolvedEvidence) -> set[UUID]:
        return set(resolved.citation.cell_ids)

    @staticmethod
    def _artifact_descriptor(item: ContentArtifact) -> EvidenceArtifactDescriptor:
        return EvidenceArtifactDescriptor(
            id=item.id,
            kind=item.kind,
            media_type=item.media_type,
            byte_size=item.byte_size,
            content_sha256=item.content_sha256,
            pixel_width=item.pixel_width,
            pixel_height=item.pixel_height,
            producer_name=item.producer_name,
            producer_revision=item.producer_revision,
            schema_revision=item.schema_revision,
            prompt_revision=item.prompt_revision,
            validation_state=item.validation_state,
            provenance_class=_provenance_class(item.kind),
        )

    @staticmethod
    def _table_descriptor(
        resolved: _ResolvedEvidence, cited_cell_ids: set[UUID]
    ) -> EvidenceTableDescriptor | None:
        if resolved.table is None:
            return None
        available_cell_ids = {cell.id for cell in resolved.cells}
        header_associations: dict[UUID, list[UUID]] = {}
        for cell in resolved.cells:
            try:
                associations = [UUID(value) for value in cell.header_associations]
            except (AttributeError, TypeError, ValueError) as exc:
                raise EvidenceNotFoundError from exc
            if any(value not in available_cell_ids for value in associations):
                raise EvidenceNotFoundError
            header_associations[cell.id] = associations
        return EvidenceTableDescriptor(
            id=resolved.table.id,
            validation_state=resolved.table.validation_state,
            validation_codes=resolved.table.validation_codes,
            structure_schema_revision=resolved.table.structure_schema_revision,
            row_count=resolved.table.row_count,
            column_count=resolved.table.column_count,
            header_row_count=resolved.table.header_row_count,
            columns=[
                EvidenceTableColumn(
                    id=item.id,
                    column_index=item.column_index,
                    header=item.raw_header,
                    logical_type=item.logical_type,
                    unit=item.unit,
                    currency=item.currency,
                )
                for item in resolved.columns
            ],
            cells=[
                EvidenceTableCell(
                    id=item.id,
                    row_index=item.row_index,
                    column_index=item.column_index,
                    row_span=item.row_span,
                    column_span=item.column_span,
                    is_header=item.is_header,
                    header_associations=header_associations[item.id],
                    text=item.raw_text,
                    normalized_value=item.normalized_value,
                    logical_type=item.logical_type,
                    unit=item.unit,
                    currency=item.currency,
                    cited=item.id in cited_cell_ids,
                )
                for item in resolved.cells
            ],
        )

    @staticmethod
    def _calculation_descriptor(
        resolved: _ResolvedEvidence,
    ) -> EvidenceCalculationDescriptor | None:
        trace = resolved.trace
        if trace is None:
            return None
        if not (
            len(trace.cell_ids)
            == len(trace.operand_values)
            == len(trace.operand_types)
        ):
            raise EvidenceNotFoundError
        cell_by_id = {cell.id: cell for cell in resolved.cells}
        column_by_index = {column.column_index: column for column in resolved.columns}
        operands: list[EvidenceCalculationOperand] = []
        for cell_id, value, logical_type in zip(
            trace.cell_ids, trace.operand_values, trace.operand_types, strict=True
        ):
            try:
                parsed_cell_id = UUID(cell_id)
            except (AttributeError, TypeError, ValueError) as exc:
                raise EvidenceNotFoundError from exc
            cell = cell_by_id.get(parsed_cell_id)
            if cell is None:
                raise EvidenceNotFoundError
            source_value = (
                cell.normalized_value
                if cell.normalized_value is not None
                else cell.raw_text
            )
            if value != source_value or logical_type != cell.logical_type:
                raise EvidenceNotFoundError
            column = column_by_index.get(cell.column_index)
            header = column.raw_header if column is not None else "Table value"
            operands.append(
                EvidenceCalculationOperand(
                    cell_id=cell.id,
                    label=f"{header}, row {cell.row_index + 1}",
                    value=value,
                    logical_type=logical_type,
                )
            )
        return EvidenceCalculationDescriptor(
            trace_id=trace.id,
            operator=trace.operator,
            operator_revision=trace.operator_revision,
            operands=operands,
            unit=trace.unit,
            currency=trace.currency,
            rounding_rule=trace.rounding_rule,
            result_type=trace.result_type,
            result_value=trace.result_value,
        )

    def _require(self, user: User, workspace_id: UUID, action, resource) -> None:
        try:
            self._policy.require(
                user=user,
                workspace_id=workspace_id,
                action=action,
                resource=resource,
            )
        except (PolicyDeniedError, PolicyNotFoundError) as exc:
            raise EvidenceNotFoundError from exc


def _provenance_class(
    kind: str,
) -> Literal["source", "extracted", "generated", "derived"]:
    if kind in {ArtifactKind.PAGE_RENDER.value, ArtifactKind.REGION_CROP.value}:
        return "source"
    if kind in {
        ArtifactKind.OCR_TEXT.value,
        ArtifactKind.SOURCE_CAPTION.value,
        ArtifactKind.STRUCTURED_TABLE.value,
    }:
        return "extracted"
    if kind == ArtifactKind.GENERATED_DESCRIPTION.value:
        return "generated"
    return "derived"


def _extension(media_type: str) -> str:
    if media_type.startswith("image/png"):
        return "png"
    if media_type.startswith("text/csv"):
        return "csv"
    if media_type.startswith("text/plain"):
        return "txt"
    return "json"
