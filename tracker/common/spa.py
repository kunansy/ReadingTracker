from pathlib import Path

from fastapi.responses import FileResponse

from tracker.common.logger import logger


SPA_DIR = Path("static/app-spa")
SPA_INDEX = SPA_DIR / "index.html"


def spa_response() -> FileResponse:
    return FileResponse(SPA_INDEX, media_type="text/html")


def check_spa_bundle(index: Path) -> bool:
    if index.exists():
        return True

    logger.warning("SPA bundle not found at %s, run `npm run build`", index)
    return False
