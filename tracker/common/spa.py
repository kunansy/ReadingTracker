from pathlib import Path

import anyio
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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


class SpaStaticFiles(StaticFiles):
    # An unbuilt bundle must answer 404, not the RuntimeError the base class raises.
    async def check_config(self) -> None:
        if self.directory is not None and not await anyio.Path(self.directory).exists():
            return
        await super().check_config()


# Must be included after every other route: it answers any remaining GET.
@router.get("/{path:path}", include_in_schema=False)
async def spa_catch_all(path: str) -> FileResponse:
    if path.split("/", 1)[0] in NOT_SPA_PREFIXES:
        raise HTTPException(status_code=404, detail="Not found")
    if not SPA_INDEX.exists():
        raise HTTPException(status_code=503, detail="SPA bundle is not built")
    return spa_response()
