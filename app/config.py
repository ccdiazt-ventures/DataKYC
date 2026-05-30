"""DataKYC configuration from environment variables."""
from __future__ import annotations

import secrets
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8002
    api_reload: bool = False
    api_log_level: str = "info"

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://datakyc:datakyc_secret@localhost:5433/datakyc"

    # Redis
    redis_url: str = "redis://localhost:6380/0"

    # Spark Vision Models
    granite_vision_url: str = "http://10.0.0.100:8004/v1"
    gemma4_url: str = "http://10.0.0.100:8003/v1"
    vision_timeout_seconds: int = 30

    # Security
    api_key_prefix: str = "dkc"
    secret_key: str = "change-me-to-a-random-string-at-least-32-chars"

    # Tier
    default_tier: str = "FREE"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
