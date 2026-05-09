"""Materials HTTP routes: legacy HTML pages and shared action endpoints."""

from fastapi import APIRouter

from tracker.materials.action_routes import router as action_router


router = APIRouter()
router.include_router(action_router)
