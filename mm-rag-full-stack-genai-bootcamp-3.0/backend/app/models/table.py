from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class TableValidationState(StrEnum):
    VALIDATED = "validated"
    RETRIEVAL_ONLY = "retrieval_only"
    REJECTED = "rejected"


class TableLogicalType(StrEnum):
    TEXT = "text"
    INTEGER = "integer"
    DECIMAL = "decimal"
    PERCENTAGE = "percentage"
    CURRENCY = "currency"
    DATE = "date"


class CalculationOperator(StrEnum):
    LOOKUP = "lookup"
    COUNT = "count"
    SUM = "sum"
    AVERAGE = "average"
    MINIMUM = "minimum"
    MAXIMUM = "maximum"
    DIFFERENCE = "difference"
    RATIO = "ratio"


_TABLE_SCOPE_FK = (
    [
        "table_id",
        "generation_id",
        "document_version_id",
        "document_id",
        "workspace_id",
        "creation_attempt_id",
    ],
    [
        "table_regions.id",
        "table_regions.generation_id",
        "table_regions.document_version_id",
        "table_regions.document_id",
        "table_regions.workspace_id",
        "table_regions.creation_attempt_id",
    ],
)


class TableRegion(Base):
    __tablename__ = "table_regions"
    __table_args__ = (
        CheckConstraint("page_number > 0", name="ck_table_regions_page_number"),
        CheckConstraint(
            "row_count > 0 AND column_count > 0 AND header_row_count >= 0 "
            "AND header_row_count <= row_count",
            name="ck_table_regions_dimensions",
        ),
        CheckConstraint(
            "validation_state IN ('validated', 'retrieval_only', 'rejected')",
            name="ck_table_regions_validation_state",
        ),
        CheckConstraint(
            "length(structure_sha256) = 64", name="ck_table_regions_structure_hash"
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_table_regions_confidence",
        ),
        ForeignKeyConstraint(
            [
                "region_id",
                "generation_id",
                "document_version_id",
                "workspace_id",
                "creation_attempt_id",
            ],
            [
                "content_regions.id",
                "content_regions.generation_id",
                "content_regions.document_version_id",
                "content_regions.workspace_id",
                "content_regions.creation_attempt_id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["document_version_id", "document_id", "workspace_id"],
            [
                "document_versions.id",
                "document_versions.document_id",
                "document_versions.workspace_id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["source_crop_artifact_id", "generation_id", "workspace_id"],
            [
                "content_artifacts.id",
                "content_artifacts.generation_id",
                "content_artifacts.workspace_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["normalized_artifact_id", "generation_id", "workspace_id"],
            [
                "content_artifacts.id",
                "content_artifacts.generation_id",
                "content_artifacts.workspace_id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("region_id", name="uq_table_regions_region_id"),
        UniqueConstraint(
            "id",
            "generation_id",
            "document_version_id",
            "document_id",
            "workspace_id",
            "creation_attempt_id",
            name="uq_table_regions_scoped_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    generation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    region_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    creation_attempt_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    source_crop_artifact_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    normalized_artifact_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    header_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False)
    structure_schema_revision: Mapped[str] = mapped_column(String(40), nullable=False)
    structure_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor_name: Mapped[str] = mapped_column(String(80), nullable=False)
    extractor_revision: Mapped[str] = mapped_column(String(80), nullable=False)
    validation_state: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    validation_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TableColumn(Base):
    __tablename__ = "table_columns"
    __table_args__ = (
        CheckConstraint("column_index >= 0", name="ck_table_columns_index"),
        CheckConstraint(
            "logical_type IN ('text', 'integer', 'decimal', 'percentage', 'currency', 'date')",
            name="ck_table_columns_logical_type",
        ),
        ForeignKeyConstraint(*_TABLE_SCOPE_FK, ondelete="CASCADE"),
        UniqueConstraint("table_id", "column_index", name="uq_table_columns_position"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    generation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    creation_attempt_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    table_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    column_index: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_header: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_header: Mapped[str] = mapped_column(Text, nullable=False)
    logical_type: Mapped[str] = mapped_column(String(16), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TableCell(Base):
    __tablename__ = "table_cells"
    __table_args__ = (
        CheckConstraint(
            "row_index >= 0 AND column_index >= 0", name="ck_table_cells_position"
        ),
        CheckConstraint(
            "row_span > 0 AND column_span > 0", name="ck_table_cells_span"
        ),
        CheckConstraint(
            "logical_type IN ('text', 'integer', 'decimal', 'percentage', 'currency', 'date')",
            name="ck_table_cells_logical_type",
        ),
        CheckConstraint(
            "(bbox_x IS NULL AND bbox_y IS NULL AND bbox_width IS NULL AND bbox_height IS NULL) "
            "OR (bbox_x >= 0 AND bbox_y >= 0 AND bbox_width > 0 AND bbox_height > 0 "
            "AND bbox_x + bbox_width <= 1.000001 AND bbox_y + bbox_height <= 1.000001)",
            name="ck_table_cells_bbox",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_table_cells_confidence",
        ),
        ForeignKeyConstraint(*_TABLE_SCOPE_FK, ondelete="CASCADE"),
        UniqueConstraint("table_id", "row_index", "column_index", name="uq_table_cells_position"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    generation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    creation_attempt_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    table_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    column_index: Mapped[int] = mapped_column(Integer, nullable=False)
    row_span: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    column_span: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_header: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    header_associations: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    logical_type: Mapped[str] = mapped_column(String(16), nullable=False)
    normalized_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    bbox_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_width: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CalculationTrace(Base):
    __tablename__ = "calculation_traces"
    __table_args__ = (
        CheckConstraint(
            "operator IN ('lookup', 'count', 'sum', 'average', 'minimum', "
            "'maximum', 'difference', 'ratio')",
            name="ck_calculation_traces_operator",
        ),
        CheckConstraint(
            "length(query_fingerprint) = 64", name="ck_calculation_traces_query_hash"
        ),
        ForeignKeyConstraint(
            [
                "table_id",
                "generation_id",
                "document_version_id",
                "document_id",
                "workspace_id",
                "table_creation_attempt_id",
            ],
            [
                "table_regions.id",
                "table_regions.generation_id",
                "table_regions.document_version_id",
                "table_regions.document_id",
                "table_regions.workspace_id",
                "table_regions.creation_attempt_id",
            ],
            ondelete="CASCADE",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    generation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    table_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    region_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    table_creation_attempt_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    operator: Mapped[str] = mapped_column(String(16), nullable=False)
    operator_revision: Mapped[str] = mapped_column(String(40), nullable=False)
    cell_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    operand_types: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    operand_values: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    rounding_rule: Mapped[str] = mapped_column(String(80), nullable=False)
    result_type: Mapped[str] = mapped_column(String(16), nullable=False)
    result_value: Mapped[str] = mapped_column(Text, nullable=False)
    query_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
