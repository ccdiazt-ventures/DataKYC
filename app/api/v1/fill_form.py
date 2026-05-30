"""Form filling endpoint — maps extracted data to KYC form templates."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_db
from app.models.organization import Organization
from app.schemas.extraction import (
    FilledField,
    FillFormRequest,
    FillFormResult,
)
from app.services.form_filler import fill_form
from app.services.tier_service import get_tier_config

router = APIRouter(tags=["form-filling"])


@router.post("/fill-form", response_model=FillFormResult)
async def fill_kyc_form(
    body: FillFormRequest,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
):
    """Fill a KYC form template using extracted document data.

    Requires **BASIC** plan or higher.

    Supported templates:
    - **sofom_standard**: Standard SOFOM onboarding form
    - **cnbv_basic**: CNBV basic identification form
    - **cnbv_advanced**: CNBV advanced form with employment data
    """
    # Tier gating: BASIC+
    config = get_tier_config(org.plan)
    if not config.get("fill_form", False):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Form filling requires BASIC or higher plan",
                "code": "FEATURE_NOT_AVAILABLE",
                "current_plan": org.plan,
            },
        )

    result = fill_form(
        extracted_data=body.extracted_data,
        form_template=body.form_template,
    )

    filled_fields = [
        FilledField(**f) for f in result["filled_fields"]
    ]

    return FillFormResult(
        form_template=result["form_template"],
        filled_fields=filled_fields,
        missing_fields=result["missing_fields"],
        warnings=result["warnings"],
    )
