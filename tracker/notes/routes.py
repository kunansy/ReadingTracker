"""Notes HTTP routes: legacy HTML, JSON/action endpoints, and merged router."""

from fastapi import APIRouter

from tracker.notes.action_routes import router as action_router
from tracker.notes.html_routes import (
    get_note,
    get_notes,
    router as html_router,
)


router = APIRouter()
router.include_router(html_router)
router.include_router(action_router)

__all__ = ["get_note", "get_notes", "router"]
