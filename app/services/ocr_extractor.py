"""OCR extraction service — orchestrates document extraction via Vision AI."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DocumentType, ExtractionStatus
from app.models.extraction import ExtractionLog
from app.services.vision_client import vision_client


async def extract_document(
    db: AsyncSession,
    image_base64: str,
    document_type: DocumentType,
    organization_id: uuid.UUID,
    api_key_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Extract data from a document image and log the result."""
    # Deduplication hash
    request_hash = hashlib.sha256(
        f"{organization_id}{document_type}{image_base64[:200]}".encode()
    ).hexdigest()

    result = await vision_client.extract_document(image_base64, document_type)

    # Determine status
    if result.get("error"):
        status = ExtractionStatus.FAILED
    elif result.get("overall_confidence", 0) < 0.3:
        status = ExtractionStatus.PARTIAL
    else:
        status = ExtractionStatus.SUCCESS

    # Log extraction
    log_entry = ExtractionLog(
        id=uuid.uuid4(),
        organization_id=organization_id,
        api_key_id=api_key_id,
        document_type=document_type.value,
        source_model="granite-vision:4b",
        status=status.value,
        request_hash=request_hash,
        processing_time_ms=result.get("processing_time_ms", 0),
        confidence_score=result.get("overall_confidence", 0.0),
        fields_extracted=result.get("fields", {}),
        error_message=result.get("error"),
    )
    db.add(log_entry)
    await db.flush()

    return {
        "extraction_id": str(log_entry.id),
        "document_type": document_type.value,
        "status": status.value,
        "source_model": "granite-vision:4b",
        "fields": result.get("fields", {}),
        "confidence_scores": result.get("confidence_scores", {}),
        "overall_confidence": result.get("overall_confidence", 0.0),
        "processing_time_ms": result.get("processing_time_ms", 0),
        "error": result.get("error"),
    }


async def cross_validate(
    front_image_b64: str | None = None,
    back_image_b64: str | None = None,
    pre_extracted_data: dict | None = None,
    front_data: dict | None = None,
    back_data: dict | None = None,
) -> dict[str, Any]:
    """Cross-validate INE extracted data using Gemma4."""
    result = await vision_client.cross_validate_ine(
        front_data=front_data,
        back_data=back_data,
        front_image_b64=front_image_b64,
        back_image_b64=back_image_b64,
        pre_extracted=pre_extracted_data,
    )
    return result
