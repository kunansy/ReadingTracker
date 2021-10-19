import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import UJSONResponse
from fastapi.staticfiles import StaticFiles

from tracker.common import database, settings
from tracker.common.log import logger
# from tracker.cards.routes import router as cards_router
# from tracker.materials.routes import router as materials_router
from tracker.notes.routes import router as notes_router
from tracker.reading_log.routes import router as reading_log_router


# TODO: make a database backup on
#  shutdown and send it to Google Drive
app = FastAPI(
    title="Reading Tracker",
    description="Reading queue, logging the reading, keep some notes",
    version=settings.API_VERSION,
    debug=settings.API_DEBUG,
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(reading_log_router)
app.include_router(notes_router)
# app.include_router(materials_router)
# app.include_router(cards_router)



@app.exception_handler(database.DatabaseError)
async def database_exception_handler(request: Request,
                                     exc: database.DatabaseError):
    logger.exception("Error with the database, %s", str(exc))
    return UJSONResponse(
        status_code=500,
        content={"message": "Internal server error"},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request,
                                       exc: RequestValidationError):
    logger.exception("Validation error occurred, %s", str(exc))
    return UJSONResponse(
        status_code=422,
        content={"message": "Validation error"},
    )


if __name__ == '__main__':
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        debug=settings.API_DEBUG
    )
