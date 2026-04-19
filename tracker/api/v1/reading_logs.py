import typing
from uuid import UUID

from fastapi import APIRouter, HTTPException

from tracker.reading_log import db, schemas


router = APIRouter(prefix="/reading_logs", tags=["reading-logs-api"])


@router.get("/", response_model=schemas.ListReadingLogsResponse)
async def list_reading_logs(req: schemas.ListReadingLogsRequest):
    items = await db.list_log_records(material_id=req.material_id)
    return {
        "items": items,
    }


@router.post("/", status_code=201, response_model=schemas.CreateReadingLogsResponse)
async def create_log_record(log: schemas.LogRecord):
    if not await db.is_record_correct(**log.model_dump()):
        raise HTTPException(status_code=400, detail="Invalid record")

    log_id = await db.insert_log_record(
        material_id=log.material_id,
        date=log.date,
        count=log.count,
    )

    return {"log_id": log_id}


@router.get("/{log_id}")
async def get_reading_log(log_id: UUID):
    # TODO: implement
    if not (log := await db.list_log_records(material_id=log_id)):
        raise HTTPException(status_code=404, detail="Log not found")

    return {"reading_log": log}


@router.patch("/{log_id}")
async def update_reading_log(log_id: UUID, body: typing.Any):
    raise NotImplementedError
