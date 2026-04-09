import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette_exporter import PrometheusMiddleware, handle_metrics

from tracker.api.v1.materials import router as api_v1_materials_router
from tracker.api.v1.notes import router as api_v1_notes_router
from tracker.cards.routes import router as cards_router
from tracker.common import database, keydb_api, manticoresearch, settings
from tracker.common.logger import logger
from tracker.materials.action_routes import router as materials_action_router
from tracker.materials.html_routes import router as materials_html_router
from tracker.materials.spa import router as materials_spa_router
from tracker.notes.action_routes import router as notes_action_router
from tracker.notes.html_routes import (
    note_detail_router as notes_note_detail_router,
    router as notes_html_router,
)
from tracker.notes.spa import router as notes_spa_router
from tracker.reading_log.routes import router as reading_log_router
from tracker.system.routes import router as system_router


async def _init_cache():
    if not await keydb_api.healthcheck():
        logger.info("Keydb is offline")

    # TODO: remove keydb integration


async def startup():
    logger.info("Init cache")
    async with asyncio.timeout(10):
        await _init_cache()
    logger.info("Complete init")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.DEBUG_MODE:
        await startup()

    yield


app = FastAPI(
    title="Reading Tracker",
    description="Reading queue, logging the reading, keep some notes",
    version=settings.API_VERSION,
    debug=settings.API_DEBUG,
    lifespan=lifespan,
)

app.add_middleware(
    PrometheusMiddleware,
    app_name="tracker",
    prefix="tracker",
    labels={
        "server_name": os.getenv("HOSTNAME"),  # type: ignore[dict-item]
    },
    group_paths=True,
    skip_paths=["/readiness", "/liveness"],
)
app.add_route("/metrics", handle_metrics)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(api_v1_materials_router, prefix="/api/v1")
app.include_router(api_v1_notes_router, prefix="/api/v1")
app.include_router(reading_log_router)
app.include_router(notes_action_router)
app.include_router(materials_action_router)
if settings.APP_SPA_ENABLED:
    app.include_router(notes_spa_router)
    app.include_router(materials_spa_router)
    # Single-note and update pages are still server-rendered (not in React yet).
    app.include_router(notes_note_detail_router, prefix="/notes")
else:
    app.include_router(notes_html_router)
    app.include_router(materials_html_router)
app.include_router(cards_router)
app.include_router(system_router)


def _api_v1_json_detail(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, str):
        return detail
    return str(detail)


def _api_v1_validation_detail(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", ()))
        msg = err.get("msg", "")
        parts.append(f"{loc}: {msg}")
    return "; ".join(parts) if parts else repr(exc)


@app.exception_handler(database.DatabaseException)
async def database_exception_handler(request: Request, exc: database.DatabaseException):
    logger.exception("Database exception occurred, (%s), %s", request.url, str(exc))

    if request.url.path.startswith("/api/v1"):
        if isinstance(exc, database.AlreadyExistsException):
            return JSONResponse(
                status_code=409,
                content={"detail": f"Database error: {exc}"},
            )
        return JSONResponse(
            status_code=500,
            content={"detail": f"Database error: {exc}"},
        )

    context = {
        "request": request,
        "error": {
            "type": exc.__class__.__name__,
            "args": exc.args,
            "json": f"Database exception: {exc}",
        },
    }

    return templates.TemplateResponse(request, "errors/500.html", context)


@app.exception_handler(manticoresearch.ManticoreException)
async def manticore_exception_handler(
    request: Request,
    exc: manticoresearch.ManticoreException,
):
    logger.exception(
        "Manticoresearch exception occurred, (%s), %s",
        request.url,
        str(exc),
    )

    if request.url.path.startswith("/api/v1"):
        return JSONResponse(
            status_code=500,
            content={"detail": f"Manticoresearch error: {exc}"},
        )

    context = {
        "request": request,
        "error": {
            "type": exc.__class__.__name__,
            "args": exc.args,
            "json": f"Manticoresearch exception: {exc}",
        },
    }

    return templates.TemplateResponse(request, "errors/500.html", context)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.exception("Validation error occurred, (%s), %s", request.url, str(exc))

    if request.url.path.startswith("/api/v1"):
        return JSONResponse(
            status_code=422,
            content={"detail": _api_v1_validation_detail(exc)},
        )

    context = {
        "request": request,
        "error": {"type": exc.__class__.__name__, "args": exc.args, "json": repr(exc)},
    }

    return templates.TemplateResponse(request, "errors/500.html", context)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.exception("HTTP exception occurred, (%s), %s", request.url, str(exc))

    if request.url.path.startswith("/api/v1"):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": _api_v1_json_detail(exc)},
        )

    context = {"request": request, "what": repr(exc)}

    return templates.TemplateResponse(request, "errors/404.html", context)


@app.get("/liveness", include_in_schema=False)
async def liveness():
    return {"status": "ok"}


@app.get("/readiness", include_in_schema=False)
async def readiness():
    status_code = 500

    async with asyncio.TaskGroup() as tg:
        db_readiness = tg.create_task(database.readiness())
        manticore_readiness = tg.create_task(manticoresearch.readiness())

    if db_readiness.result() is manticore_readiness.result() is True:
        status_code = 200

    status = {
        "is_db_ready": db_readiness.result(),
        "is_manticore_ready": manticore_readiness.result(),
    }
    return JSONResponse(content=status, status_code=status_code)


async def init() -> None:
    await database.create_db()
    await manticoresearch.init()


if __name__ == "__main__":
    asyncio.run(init())
