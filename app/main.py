"""DataKYC — Document Data Extraction API for KYC Onboarding.

Specialized in extracting structured data from Mexican identity and financial
documents using Vision AI models (Granite Vision 4.1 + Gemma4 26B) on DGX Spark.

BiometriKYC-compatible tier system with API key authentication.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import router as v1_router
from app.config import get_settings
from app.database import engine, Base
from app.middleware.error_handler import register_error_handlers

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables. Shutdown: dispose engine."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="DataKYC",
    description=__doc__,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register error handlers
register_error_handlers(app)

# Serve static files: frontend + test images
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
TEST_IMAGES_DIR = Path(__file__).resolve().parent.parent.parent / "datatest"

if WEB_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(WEB_DIR)), name="assets")

if TEST_IMAGES_DIR.exists():
    app.mount("/test-images", StaticFiles(directory=str(TEST_IMAGES_DIR)), name="test_images")


@app.get("/")
async def serve_frontend():
    """Serve the DataKYC web interface."""
    index_path = WEB_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "DataKYC API — frontend not found. Visit /docs for API documentation."}

# Include routers
app.include_router(v1_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level=settings.api_log_level,
    )
