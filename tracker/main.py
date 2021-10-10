import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import UJSONResponse
from fastapi.staticfiles import StaticFiles

from tracker.common import database, settings
from tracker.common.log import logger
from tracker.materials.routes import router as materials_router


# TODO: make a database backup on
#  shutdown and send it to Google Drive
app = FastAPI(
    title="Reading Tracker",
    description="Reading queue, logging the reading, keep some notes",
    version=settings.API_VERSION,
    debug=settings.API_DEBUG,
)

app.include_router(materials_router)

app.mount("/static", StaticFiles(directory="static"), name="static")


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
        port=settings.API_PORT,
        debug=settings.API_DEBUG
    )
