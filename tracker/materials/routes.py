"""Materials HTTP routes: legacy HTML pages and shared action endpoints."""

from fastapi import APIRouter

from tracker.materials.action_routes import router as action_router
from tracker.materials.html_routes import router as html_router


router = APIRouter()
router.include_router(html_router)
router.include_router(action_router)
