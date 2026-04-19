import typing
from uuid import UUID

from fastapi import APIRouter, HTTPException

from tracker.reading_log import db, schemas


router = APIRouter(prefix="/reading_logs", tags=["reading-logs-api"])


@router.get("/", response_model=schemas.ListReadingLogsResponse)
async def list_reading_logs(material_id: UUID | None = None):
    items = await db.list_log_records(material_id=material_id)
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


@router.get("/{log_id}", response_model=schemas.LogRecord)
async def get_reading_log(log_id: UUID):
    reading_log = await db.get_log_record(log_id=log_id)
    return {"reading_log": reading_log}


@router.patch("/{log_id}")
async def update_reading_log(log_id: UUID, body: typing.Any):
    raise NotImplementedError
