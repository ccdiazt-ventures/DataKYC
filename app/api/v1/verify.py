"""Verification endpoints — cross-validation of extracted data."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_db
from app.models.organization import Organization
from app.schemas.extraction import (
    Discrepancy,
    VerifyIneRequest,
    VerifyIneResult,
)
from app.services.cross_validator import validate_ine_data
from app.services.tier_service import get_tier_config

router = APIRouter(tags=["verification"])


@router.post("/verify/ine-data", response_model=VerifyIneResult)
async def verify_ine(
    body: VerifyIneRequest,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
):
    """Cross-validate INE extracted data using Gemma4 26B.

    Requires **PRO** or **ENTERPRISE** tier.

    You can provide either:
    - **pre_extracted_data**: JSON with previously extracted INE fields
    - **front_image_base64** + **back_image_base64**: raw images for fresh extraction + validation

    Returns consistency check results with discrepancies and recommendations.
    """
    # Tier gating: PRO+ only
    config = get_tier_config(org.plan)
    if not config.get("cross_validation", False):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Cross-validation requires PRO or ENTERPRISE plan",
                "code": "FEATURE_NOT_AVAILABLE",
                "current_plan": org.plan,
            },
        )

    # Need either pre_extracted data or images
    if not body.pre_extracted_data and not body.front_image_base64:
        raise HTTPException(
            status_code=400,
            detail="Provide either pre_extracted_data or front_image_base64",
        )

    # If images provided, extract first then validate
    if body.front_image_base64 and not body.pre_extracted_data:
        from app.services.vision_client import vision_client
        from app.core.constants import DocumentType

        front_result = await vision_client.extract_document(
            body.front_image_base64, DocumentType.INE_FRONT
        )
        back_result = None
        if body.back_image_base64:
            back_result = await vision_client.extract_document(
                body.back_image_base64, DocumentType.INE_BACK
            )

        pre_extracted = front_result.get("fields", {})
        if back_result:
            pre_extracted["back"] = back_result.get("fields", {})
    else:
        pre_extracted = body.pre_extracted_data or {}

    result = await validate_ine_data(pre_extracted_data=pre_extracted)

    discrepancies = []
    for d in result.get("discrepancies", []):
        discrepancies.append(Discrepancy(
            field=d.get("field", ""),
            extracted_value=str(d.get("extracted_value", "")),
            validated_value=str(d.get("expected", "")),
            confidence=d.get("severity", "medium") == "low" and 0.9 or 0.5,
        ))

    return VerifyIneResult(
        validation_id=uuid.uuid4(),
        is_consistent=result.get("is_consistent", False),
        overall_confidence=result.get("overall_confidence", 0.0),
        discrepancies=discrepancies,
        validated_fields=result.get("validated_fields", {}),
        recommendations=result.get("recommendations", []),
    )
