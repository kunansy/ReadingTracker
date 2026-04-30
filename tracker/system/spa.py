from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse


SPA_INDEX = Path("static/app-spa/index.html")

router = APIRouter(prefix="/system", tags=["system-spa"])


def _spa_response() -> FileResponse:
    return FileResponse(SPA_INDEX, media_type="text/html")


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
async def system_spa_root() -> FileResponse:
    return _spa_response()


@router.get("/{full_path:path}", include_in_schema=False)
async def system_spa_catchall(full_path: str) -> FileResponse:  # noqa: ARG001
    return _spa_response()
