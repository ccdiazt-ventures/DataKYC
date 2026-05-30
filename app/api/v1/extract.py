"""Extraction endpoints — document OCR and data extraction."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_api_key, get_current_organization, get_db
from app.core.constants import DocumentType
from app.models.api_key import ApiKey
from app.models.organization import Organization
from app.schemas.extraction import (
    ExtractionResult,
    ExtractRequest,
)
from app.services.ocr_extractor import extract_document
from app.services.tier_service import (
    check_and_increment_quota,
    is_doc_type_allowed,
    get_tier_config,
)

router = APIRouter(tags=["extraction"])


@router.post("/extract/{doc_type}", response_model=ExtractionResult)
async def extract_document_data(
    doc_type: DocumentType,
    body: ExtractRequest,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
    api_key: ApiKey = Depends(get_current_api_key),
):
    """Extract structured data from a document image using Granite Vision 4.1.

    Supported document types depend on your plan tier:
    - **FREE**: INE_FRONT only
    - **BASIC**: INE_FRONT, INE_BACK, CURP, RFC
    - **PRO/ENTERPRISE**: All document types

    Returns extracted fields with per-field confidence scores.
    """
    # Tier gating: check document type is allowed
    if not is_doc_type_allowed(org.plan, doc_type):
        config = get_tier_config(org.plan)
        allowed = config["document_types"]
        raise HTTPException(
            status_code=403,
            detail={
                "error": f"Document type '{doc_type.value}' not available in {org.plan} plan",
                "code": "DOCUMENT_TYPE_NOT_ALLOWED",
                "current_plan": org.plan,
                "allowed_types": allowed,
            },
        )

    # Quota check
    allowed, error_msg = await check_and_increment_quota(db, org)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": error_msg,
                "code": "QUOTA_EXCEEDED",
            },
        )

    # Extract
    result = await extract_document(
        db=db,
        image_base64=body.image_base64,
        document_type=doc_type,
        organization_id=org.id,
        api_key_id=api_key.id,
    )

    if result.get("error"):
        return ExtractionResult(
            extraction_id=uuid.UUID(result["extraction_id"]),
            document_type=doc_type.value,
            status="FAILED",
            source_model="granite-vision:4b",
            fields={},
            confidence_scores={},
            overall_confidence=0.0,
            processing_time_ms=result.get("processing_time_ms", 0),
            created_at=__import__("datetime").datetime.utcnow(),
        )

    return ExtractionResult(
        extraction_id=uuid.UUID(result["extraction_id"]),
        document_type=doc_type.value,
        status=result["status"],
        source_model=result["source_model"],
        fields=result["fields"],
        confidence_scores=result["confidence_scores"],
        overall_confidence=result["overall_confidence"],
        processing_time_ms=result["processing_time_ms"],
        created_at=__import__("datetime").datetime.utcnow(),
    )
