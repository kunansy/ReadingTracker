from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse


# React-only paths.
SPA_INDEX = Path("static/app-spa/index.html")

router = APIRouter(prefix="/notes", tags=["notes-spa"])


def _spa_response() -> FileResponse:
    return FileResponse(SPA_INDEX, media_type="text/html")


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
async def notes_spa_root() -> FileResponse:
    return _spa_response()


@router.get("/add-view", include_in_schema=False)
async def notes_spa_add_view() -> FileResponse:
    return _spa_response()


@router.get("/graph", include_in_schema=False)
async def notes_spa_graph() -> FileResponse:
    return _spa_response()


@router.get("/{path:path}", include_in_schema=False)
async def notes_spa_catch_all(path: str) -> FileResponse:  # noqa: ARG001
    return _spa_response()
