"""Tier-based rate limiting middleware.

Uses Redis for distributed rate limiting with tier-specific RPM limits.
"""

from __future__ import annotations

import time
from uuid import UUID

from fastapi import HTTPException, Request

from app.services.tier_service import get_tier_config


async def check_rate_limit(
    organization_id: UUID,
    plan: str,
    redis_client,
) -> None:
    """Check if the organization has exceeded their tier's rate limit.

    Uses a sliding window approach with Redis sorted sets.
    """
    config = get_tier_config(plan)
    rpm = config["rate_per_minute"]
    window_seconds = 60

    key = f"rate:{organization_id}"
    now_ms = int(time.time() * 1000)
    window_start_ms = now_ms - (window_seconds * 1000)

    try:
        # Remove entries outside the window
        await redis_client.zremrangebyscore(key, 0, window_start_ms)
        # Count current
        count = await redis_client.zcard(key)

        if count >= rpm:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Tier rate limit exceeded",
                    "code": "TIER_RATE_LIMIT",
                    "retry_after_seconds": 60,
                    "limit": rpm,
                    "current": count,
                },
            )

        # Add current request
        await redis_client.zadd(key, {str(now_ms): now_ms})
        await redis_client.expire(key, window_seconds + 5)

    except HTTPException:
        raise
    except Exception:
        # Redis unavailable — allow request through (fail open)
        pass
