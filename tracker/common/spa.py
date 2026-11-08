from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from tracker.common.logger import logger


SPA_DIR = Path("static/app-spa")
SPA_INDEX = SPA_DIR / "index.html"
NOT_SPA_PREFIXES = frozenset({"api", "static"})

router = APIRouter(tags=["spa"])


def spa_response() -> FileResponse:
    return FileResponse(SPA_INDEX, media_type="text/html")


def check_spa_bundle(index: Path) -> bool:
    if index.exists():
        return True

    logger.warning("SPA bundle not found at %s, run `npm run build`", index)
    return False


# Must be included after every other route: it answers any remaining GET.
@router.get("/{path:path}", include_in_schema=False)
async def spa_catch_all(path: str) -> FileResponse:
    if path.split("/", 1)[0] in NOT_SPA_PREFIXES:
        raise HTTPException(status_code=404, detail="Not found")
    return spa_response()
