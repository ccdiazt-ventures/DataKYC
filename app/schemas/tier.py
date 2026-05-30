"""Tier configuration schemas."""

from pydantic import BaseModel


class TierFeatures(BaseModel):
    rate_per_minute: int
    extractions_per_month: int  # -1 = unlimited
    document_types: list[str]
    cross_validation: bool
    fill_form: bool
    batch_processing: bool


class TierConfig(BaseModel):
    name: str
    features: TierFeatures
