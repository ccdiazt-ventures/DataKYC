"""v1 API router — aggregates all v1 endpoint groups."""

from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.extract import router as extract_router
from app.api.v1.fill_form import router as fill_form_router
from app.api.v1.health import router as health_router
from app.api.v1.verify import router as verify_router

router = APIRouter(prefix="/api/v1")

router.include_router(health_router)
router.include_router(auth_router)
router.include_router(extract_router)
router.include_router(verify_router)
router.include_router(fill_form_router)
router.include_router(admin_router)
