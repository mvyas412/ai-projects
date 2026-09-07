from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

EvidenceKind = Literal[
    "text", "figure", "chart", "diagram", "image", "table", "calculation"
]


class EvidenceArtifactDescriptor(BaseModel):
    id: UUID
    kind: str
    media_type: str
    byte_size: int
    content_sha256: str
    pixel_width: int | None = None
    pixel_height: int | None = None
    producer_name: str
    producer_revision: str
    schema_revision: str
    prompt_revision: str | None = None
    validation_state: str
    provenance_class: Literal["source", "extracted", "generated", "derived"]


class EvidenceRegionDescriptor(BaseModel):
    id: UUID
    kind: str
    page_number: int
    bbox_x: float
    bbox_y: float
    bbox_width: float
    bbox_height: float
    page_width: float
    page_height: float
    rotation: int
    extractor_name: str
    extractor_revision: str
    locator_schema_revision: str
    confidence: float | None = None


class EvidenceTableColumn(BaseModel):
    id: UUID
    column_index: int
    header: str
    logical_type: str
    unit: str | None = None
    currency: str | None = None


class EvidenceTableCell(BaseModel):
    id: UUID
    row_index: int
    column_index: int
    row_span: int
    column_span: int
    is_header: bool
    header_associations: list[UUID]
    text: str
    normalized_value: str | None = None
    logical_type: str
    unit: str | None = None
    currency: str | None = None
    cited: bool = False


class EvidenceTableDescriptor(BaseModel):
    id: UUID
    validation_state: str
    validation_codes: list[str]
    structure_schema_revision: str
    row_count: int
    column_count: int
    header_row_count: int
    columns: list[EvidenceTableColumn]
    cells: list[EvidenceTableCell]


class EvidenceCalculationOperand(BaseModel):
    cell_id: UUID
    label: str
    value: str
    logical_type: str


class EvidenceCalculationDescriptor(BaseModel):
    trace_id: UUID
    operator: str
    operator_revision: str
    operands: list[EvidenceCalculationOperand]
    unit: str | None = None
    currency: str | None = None
    rounding_rule: str
    result_type: str
    result_value: str


class EvidenceDescriptor(BaseModel):
    schema_revision: Literal["evidence-v1"] = "evidence-v1"
    citation_index: int = Field(ge=0)
    evidence_kind: EvidenceKind
    document_id: UUID
    document_version_id: UUID
    generation_id: UUID | None = None
    document_title: str
    page_number: int | None = None
    excerpt: str
    region: EvidenceRegionDescriptor | None = None
    artifacts: list[EvidenceArtifactDescriptor] = Field(default_factory=list)
    table: EvidenceTableDescriptor | None = None
    calculation: EvidenceCalculationDescriptor | None = None
