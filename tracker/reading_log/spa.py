from fastapi import APIRouter
from fastapi.responses import FileResponse

from tracker.common.spa import spa_response


router = APIRouter(prefix="/reading_logs", tags=["reading-logs-spa"])


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
async def reading_logs_spa_root() -> FileResponse:
    return spa_response()


@router.get("/{full_path:path}", include_in_schema=False)
async def reading_logs_spa_catchall(full_path: str) -> FileResponse:  # noqa: ARG001
    return spa_response()
