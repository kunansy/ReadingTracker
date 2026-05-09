import asyncio
from uuid import UUID

from fastapi import APIRouter, HTTPException

from tracker.reading_log import db, schemas
from tracker.materials import db as materials_db


router = APIRouter(prefix="/reading_logs", tags=["reading-logs-api"])


@router.get("/", response_model=schemas.ListReadingLogsResponse)
async def list_reading_logs(material_id: UUID | None = None):
    items = await db.list_log_records(material_id=material_id)
    return {
        "items": items,
    }


@router.post("/", status_code=201, response_model=schemas.CreateReadingLogsResponse)
async def create_log_record(log: schemas.CreateReadingLogsRequest):
    try:
        await db.check_record_correct(material_id=log.material_id, date=log.date, count=log.count)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    log_id = await db.insert_log_record(
        material_id=log.material_id,
        date=log.date,
        count=log.count,
    )

    return {"log_id": log_id}



@router.get("/material-reading-now", response_model=schemas.GetMaterialReadingNowResponse)
async def get_material_reading_now():
    if material_id := await db.get_material_reading_now():
        return {
            "material_id": material_id,
        }

    raise HTTPException(status_code=404, detail="No materials reading now found")
