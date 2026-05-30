"""Cross-validator service using Gemma4 for INE data consistency checking."""

from __future__ import annotations

from app.schemas.extraction import VerifyIneResult as VerifyIneResultSchema
from app.services.vision_client import vision_client


async def validate_ine_data(
    front_image_b64: str | None = None,
    back_image_b64: str | None = None,
    pre_extracted_data: dict | None = None,
) -> dict:
    """Validate extracted INE data using Gemma4 for consistency checks."""
    result = await vision_client.cross_validate_ine(
        front_image_b64=front_image_b64,
        back_image_b64=back_image_b64,
        pre_extracted=pre_extracted_data,
    )
    return result
