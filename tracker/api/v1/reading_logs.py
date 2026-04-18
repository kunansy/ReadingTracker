import typing
from uuid import UUID

from fastapi import APIRouter, HTTPException

from tracker.reading_log import db, schemas


router = APIRouter(prefix="/reading_logs", tags=["reading-logs-api"])


@router.get("/reading_logs")
async def get_reading_logs(req: schemas.GetReadingLogsRequest):
    items = await db.get_log_records(material_id=req.material_id)
    return {
        "items": items,
    }


@router.post("/", status_code=201, response_model=schemas.LogRecord)
async def create_log_record(log: schemas.LogRecord):
    # TODO:
    log_id = await db.insert_log_record(  # type: ignore[func-returns-value]
        material_id=str(log.material_id),
        date=log.date,
        count=log.count,
    )

    return {"log_id": log_id}


@router.get("/{log_id}")
async def get_reading_log(log_id: UUID):
    # TODO: implement
    if not (log := await db.get_log_records(material_id=log_id)):
        raise HTTPException(status_code=404, detail="Log not found")

    return {"reading_log": log}


@router.patch("/{log_id}")
async def update_reading_log(log_id: UUID, body: typing.Any):
    raise NotImplementedError
