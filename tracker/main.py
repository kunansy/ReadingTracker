import asyncio

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import ORJSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from tracker.cards.routes import router as cards_router
from tracker.common import database, settings, manticoresearch
from tracker.common.log import logger
from tracker.materials.routes import router as materials_router
from tracker.notes.routes import router as notes_router
from tracker.reading_log.routes import router as reading_log_router
from tracker.system.routes import router as system_router


app = FastAPI(
    title="Reading Tracker",
    description="Reading queue, logging the reading, keep some notes",
    version=settings.API_VERSION,
    debug=settings.API_DEBUG,
    default_response_class=ORJSONResponse
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(reading_log_router)
app.include_router(notes_router)
app.include_router(materials_router)
app.include_router(cards_router)
app.include_router(system_router)


@app.exception_handler(database.DatabaseException)
async def database_exception_handler(request: Request,
                                     exc: database.DatabaseException):
    logger.exception("Database exception occurred, (%s), %s", request.url, str(exc))

    context = {
        "request": request,
        "error": {
            "type": exc.__class__.__name__,
            "args": exc.args,
            "json": f"Database exception: {exc}"
        }
    }

    return templates.TemplateResponse("errors/500.html", context)


@app.exception_handler(manticoresearch.ManticoreException)
async def manticore_exception_handler(request: Request,
                                      exc: manticoresearch.ManticoreException):
    logger.exception("Manticoresearch exception occurred, (%s), %s", request.url, str(exc))

    context = {
        "request": request,
        "error": {
            "type": exc.__class__.__name__,
            "args": exc.args,
            "json": f"Manticoresearch exception: {exc}"
        }
    }

    return templates.TemplateResponse("errors/500.html", context)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request,
                                       exc: RequestValidationError):
    logger.exception("Validation error occurred, (%s), %s",
                     request.url, str(exc))

    context = {
        "request": request,
        "error": {
            "type": exc.__class__.__name__,
            "args": exc.args,
            "json": exc.json(indent=4)
        }
    }

    return templates.TemplateResponse("errors/500.html", context)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request,
                                 exc: HTTPException):
    logger.exception("HTTP exception occurred, (%s), %s",
                     request.url, str(exc))

    context = {
        "request": request,
        "what": repr(exc)
    }

    return templates.TemplateResponse("errors/404.html", context)


@app.get('/liveness',
         include_in_schema=False)
async def liveness():
    return ORJSONResponse(
        content={"status": "ok"}
    )


@app.get('/readiness',
         include_in_schema=False)
async def readiness():
    status_code = 500

    async with asyncio.TaskGroup() as tg:
        db_readiness = tg.create_task(database.readiness())
        manticore_readiness = tg.create_task(manticoresearch.readiness())

    if db_readiness.result() is manticore_readiness.result() is True:
        status_code = 200

    return ORJSONResponse(
        content={},
        status_code=status_code
    )


async def init() -> None:
    await database.create_db()
    await manticoresearch.init()


if __name__ == '__main__':
    asyncio.run(init())
