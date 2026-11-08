from fastapi import APIRouter
from fastapi.responses import FileResponse

from tracker.common.spa import spa_response


router = APIRouter(prefix="/notes", tags=["notes-spa"])


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
async def notes_spa_root() -> FileResponse:
    return spa_response()


@router.get("/{path:path}", include_in_schema=False)
async def notes_spa_catch_all(path: str) -> FileResponse:  # noqa: ARG001
    return spa_response()
