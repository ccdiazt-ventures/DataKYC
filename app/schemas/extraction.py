"""Extraction request/response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.constants import DocumentType, FormTemplate


class ExtractRequest(BaseModel):
    image_base64: str = Field(..., description="Base64-encoded document image")
    context_data: dict | None = Field(default=None, description="Optional context for cross-validation")


class ExtractionResult(BaseModel):
    extraction_id: UUID
    document_type: str
    status: str
    source_model: str
    fields: dict = Field(default_factory=dict)
    confidence_scores: dict[str, float] = Field(default_factory=dict)
    overall_confidence: float = 0.0
    processing_time_ms: int = 0
    created_at: datetime


class VerifyIneRequest(BaseModel):
    front_image_base64: str | None = Field(default=None, description="Front INE image (optional if pre_extracted_data is provided)")
    back_image_base64: str | None = Field(default=None, description="Back INE image (optional)")
    pre_extracted_data: dict | None = Field(default=None, description="Pre-extracted data to validate (skips OCR)")


class Discrepancy(BaseModel):
    field: str
    extracted_value: str
    validated_value: str
    confidence: float


class VerifyIneResult(BaseModel):
    validation_id: UUID
    is_consistent: bool
    overall_confidence: float
    discrepancies: list[Discrepancy] = Field(default_factory=list)
    validated_fields: dict = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)


class FillFormRequest(BaseModel):
    extracted_data: dict = Field(..., description="Pre-extracted document data")
    form_template: FormTemplate = Field(default=FormTemplate.SOFOM_STANDARD)
    document_type: DocumentType | None = None


class FilledField(BaseModel):
    field_name: str
    field_label: str
    value: str
    source: str  # which extracted field populated this
    confidence: float


class FillFormResult(BaseModel):
    form_template: str
    filled_fields: list[FilledField] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
