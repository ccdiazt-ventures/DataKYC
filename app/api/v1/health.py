"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Health check including Spark model connectivity."""
    import httpx

    granite_ok = False
    gemma4_ok = False

    # Check Granite Vision
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get("http://10.0.0.100:8004/health")
            granite_ok = resp.status_code == 200
    except Exception:
        pass

    # Check Gemma4
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get("http://10.0.0.100:8003/health")
            gemma4_ok = resp.status_code == 200
    except Exception:
        pass

    return {
        "status": "healthy" if (granite_ok and gemma4_ok) else "degraded",
        "version": "1.0.0",
        "spark_models": {
            "granite_vision_4b": "online" if granite_ok else "offline",
            "gemma4_26b": "online" if gemma4_ok else "offline",
        },
        "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }
