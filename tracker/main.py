import asyncio

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import ORJSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from tracker.cards.routes import router as cards_router
from tracker.common import database, settings
from tracker.common.log import logger
from tracker.materials.routes import router as materials_router
from tracker.notes.es import index as notes_index
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


@app.exception_handler(database.DatabaseError)
async def database_exception_handler(request: Request,
                                     exc: database.DatabaseError):
    logger.exception("Error, (%s), %s", request.url, str(exc))

    context = {
        "request": request,
        "error": {
            "type": exc.__class__.__name__,
            "args": exc.args,
            "json": f"Database error: {exc}"
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

    is_db_alive_task = asyncio.create_task(database.is_alive())
    is_es_alive_task = asyncio.create_task(notes_index.healthcheck())

    await is_es_alive_task
    await is_db_alive_task

    if is_es_alive_task.result() is is_db_alive_task.result() is True:
        status_code = 200

    return ORJSONResponse(
        content={},
        status_code=status_code
    )


if __name__ == '__main__':
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        debug=settings.API_DEBUG
    )
