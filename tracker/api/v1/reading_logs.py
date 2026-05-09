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


@router.get("/reading-materials-titles", response_model=schemas.ListMaterialsTitles)
async def list_reading_materials_titles():
    items = await db.get_reading_material_titles()
    return {
        "items": items,
    }


@router.get(
    "/{material_id}/completion-info",
    response_model=schemas.GetMaterialCompletionInfoResponse,
)
async def get_material_completion_info(material_id: UUID):
    if not (completion_info := await get_completion_info(material_id)):
        raise HTTPException(status_code=404, detail="Material not found")

    return completion_info


@router.get("/material-reading-now", response_model=schemas.GetMaterialReadingNowResponse)
async def get_material_reading_now():
    if material_id := await db.get_material_reading_now():
        return {
            "material_id": material_id,
        }

    raise HTTPException(status_code=404, detail="No materials reading now found")


async def get_completion_info(
        material_id: UUID | None,
) -> schemas.CompletionInfoSchema | None:
    if not material_id:
        return None

    async with asyncio.TaskGroup() as tg:
        material_task = tg.create_task(materials_db.get_material(material_id=material_id))
        reading_logs_task = tg.create_task(db.get_log_records(material_id=material_id))

    if not (material := material_task.result()):
        return None
    reading_logs = reading_logs_task.result()

    return schemas.CompletionInfoSchema(
        material_pages=material.pages,
        material_type=material.material_type,
        pages_read=sum(record.count for record in reading_logs),
        read_days=len(reading_logs),
    )
