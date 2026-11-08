import asyncio
import os
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette_exporter import PrometheusMiddleware, handle_metrics

from tracker.api.v1.cards import router as api_v1_cards_router
from tracker.api.v1.materials import router as api_v1_materials_router
from tracker.api.v1.notes import router as api_v1_notes_router
from tracker.api.v1.reading_logs import router as api_v1_reading_logs_router
from tracker.api.v1.system import router as api_v1_system_router
from tracker.cards.spa import router as cards_spa_router
from tracker.common import database, kafka, manticoresearch, settings
from tracker.common.logger import logger
from tracker.materials.spa import router as materials_spa_router
from tracker.notes.spa import router as notes_spa_router
from tracker.reading_log.spa import router as reading_logs_spa_router
from tracker.system.spa import router as system_spa_router


app = FastAPI(
    title="Reading Tracker",
    description="Reading queue, logging the reading, keep some notes",
    version=settings.API_VERSION,
    debug=settings.API_DEBUG,
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

app.mount("/static", StaticFiles(directory="static", check_dir=False), name="static")

app.include_router(api_v1_materials_router, prefix="/api/v1")
app.include_router(api_v1_notes_router, prefix="/api/v1")
app.include_router(api_v1_reading_logs_router, prefix="/api/v1")
app.include_router(api_v1_cards_router, prefix="/api/v1")
app.include_router(api_v1_system_router, prefix="/api/v1")
app.include_router(notes_spa_router)
app.include_router(materials_spa_router)
app.include_router(reading_logs_spa_router)
app.include_router(cards_spa_router)
app.include_router(system_spa_router)


def _http_detail(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, str):
        return detail
    return str(detail)


def _validation_detail(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", ()))
        msg = err.get("msg", "")
        parts.append(f"{loc}: {msg}")
    return "; ".join(parts) if parts else repr(exc)


_CLIENT_DATABASE_ERRORS: dict[type[database.DatabaseException], tuple[int, str]] = {
    database.InvalidNextTokenException: (422, "InvalidNextToken"),
    database.AlreadyExistsException: (409, "AlreadyExistsError"),
    database.NotFoundException: (404, "NotFoundError"),
}


@app.exception_handler(database.DatabaseException)
async def database_exception_handler(request: Request, exc: database.DatabaseException):
    for exc_type, (status_code, prefix) in _CLIENT_DATABASE_ERRORS.items():
        if isinstance(exc, exc_type):
            logger.info("%s, (%s), %s", prefix, request.url, str(exc))
            return JSONResponse(
                status_code=status_code,
                content={"detail": f"{prefix}: {exc}"},
            )

    logger.exception("Database exception occurred, (%s), %s", request.url, str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": f"Database error: {exc}"},
    )


@app.exception_handler(kafka.KafkaSendError)
async def kafka_exception_handler(request: Request, exc: kafka.KafkaSendError):
    logger.exception("Kafka exception occurred, (%s), %s", request.url, str(exc))

    return JSONResponse(
        status_code=503,
        content={"detail": f"Kafka error: {exc}"},
    )


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

    return JSONResponse(
        status_code=500,
        content={"detail": f"Manticoresearch error: {exc}"},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.info("Validation error occurred, (%s), %s", request.url, str(exc))

    return JSONResponse(
        status_code=422,
        content={"detail": _validation_detail(exc)},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code < HTTPStatus.INTERNAL_SERVER_ERROR:
        logger.info("HTTP exception occurred, (%s), %s", request.url, str(exc))
    else:
        logger.error("HTTP exception occurred, (%s), %s", request.url, str(exc))

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": _http_detail(exc)},
    )


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
