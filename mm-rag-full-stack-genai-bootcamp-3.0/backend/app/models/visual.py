from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
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


class ContentRegionKind(StrEnum):
    FIGURE = "figure"
    CHART = "chart"
    DIAGRAM = "diagram"
    PHOTO = "photo"
    TABLE = "table"
    OTHER = "other"


class ArtifactKind(StrEnum):
    PAGE_RENDER = "page_render"
    REGION_CROP = "region_crop"
    OCR_TEXT = "ocr_text"
    SOURCE_CAPTION = "source_caption"
    DETERMINISTIC_CAPTION = "deterministic_caption"
    GENERATED_DESCRIPTION = "generated_description"
    STRUCTURED_TABLE = "structured_table"
    NORMALIZED_JSON = "normalized_json"
    NORMALIZED_CSV = "normalized_csv"


class ArtifactValidationState(StrEnum):
    VALIDATED = "validated"
    RETRIEVAL_ONLY = "retrieval_only"
    DIAGNOSTIC = "diagnostic"
    REJECTED = "rejected"


class ContentRegion(Base):
    __tablename__ = "content_regions"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('figure', 'chart', 'diagram', 'photo', 'table', 'other')",
            name="ck_content_regions_kind",
        ),
        CheckConstraint("page_number > 0", name="ck_content_regions_page_number"),
        CheckConstraint("ordinal >= 0", name="ck_content_regions_ordinal"),
        CheckConstraint(
            "bbox_x >= 0 AND bbox_y >= 0 AND bbox_width > 0 AND bbox_height > 0 "
            "AND bbox_x + bbox_width <= 1.000001 "
            "AND bbox_y + bbox_height <= 1.000001",
            name="ck_content_regions_normalized_bbox",
        ),
        CheckConstraint(
            "page_width > 0 AND page_height > 0",
            name="ck_content_regions_page_geometry",
        ),
        CheckConstraint(
            "rotation IN (0, 90, 180, 270)", name="ck_content_regions_rotation"
        ),
        CheckConstraint(
            "length(locator_sha256) = 64 AND length(page_render_sha256) = 64 "
            "AND length(extractor_config_sha256) = 64",
            name="ck_content_regions_hashes",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_content_regions_confidence",
        ),
        ForeignKeyConstraint(
            [
                "generation_id",
                "creation_attempt_id",
                "document_version_id",
                "workspace_id",
            ],
            [
                "ingestion_generations.id",
                "ingestion_generations.attempt_id",
                "ingestion_generations.document_version_id",
                "ingestion_generations.workspace_id",
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
        UniqueConstraint(
            "id",
            "generation_id",
            "document_version_id",
            "workspace_id",
            "creation_attempt_id",
            name="uq_content_regions_scoped_id",
        ),
        UniqueConstraint(
            "generation_id",
            "locator_sha256",
            name="uq_content_regions_generation_locator",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    generation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    creation_attempt_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_x: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_y: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_width: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_height: Mapped[float] = mapped_column(Float, nullable=False)
    page_width: Mapped[float] = mapped_column(Float, nullable=False)
    page_height: Mapped[float] = mapped_column(Float, nullable=False)
    rotation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locator_schema_revision: Mapped[str] = mapped_column(String(40), nullable=False)
    locator_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    page_render_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor_name: Mapped[str] = mapped_column(String(80), nullable=False)
    extractor_revision: Mapped[str] = mapped_column(String(80), nullable=False)
    extractor_config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ContentArtifact(Base):
    __tablename__ = "content_artifacts"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('page_render', 'region_crop', 'ocr_text', 'source_caption', "
            "'deterministic_caption', 'generated_description', 'structured_table', "
            "'normalized_json', 'normalized_csv')",
            name="ck_content_artifacts_kind",
        ),
        CheckConstraint(
            "validation_state IN ('validated', 'retrieval_only', 'diagnostic', 'rejected')",
            name="ck_content_artifacts_validation_state",
        ),
        CheckConstraint("byte_size > 0", name="ck_content_artifacts_byte_size"),
        CheckConstraint(
            "length(content_sha256) = 64", name="ck_content_artifacts_content_hash"
        ),
        CheckConstraint(
            "(pixel_width IS NULL AND pixel_height IS NULL) OR "
            "(pixel_width > 0 AND pixel_height > 0)",
            name="ck_content_artifacts_dimensions",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_content_artifacts_confidence",
        ),
        ForeignKeyConstraint(
            [
                "generation_id",
                "creation_attempt_id",
                "document_version_id",
                "workspace_id",
            ],
            [
                "ingestion_generations.id",
                "ingestion_generations.attempt_id",
                "ingestion_generations.document_version_id",
                "ingestion_generations.workspace_id",
            ],
            ondelete="CASCADE",
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
            ["parent_artifact_id", "generation_id", "workspace_id"],
            [
                "content_artifacts.id",
                "content_artifacts.generation_id",
                "content_artifacts.workspace_id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "id", "generation_id", "workspace_id", name="uq_content_artifacts_scoped_id"
        ),
        UniqueConstraint("object_key", name="uq_content_artifacts_object_key"),
        UniqueConstraint(
            "region_id", "kind", "content_sha256", name="uq_content_artifacts_region_kind_hash"
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
    parent_artifact_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    creation_attempt_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    pixel_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pixel_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    producer_name: Mapped[str] = mapped_column(String(80), nullable=False)
    producer_revision: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_revision: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_revision: Mapped[str | None] = mapped_column(String(80), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    validation_state: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
