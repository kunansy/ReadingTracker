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
async def create_log_record(log: schemas.CreateReadingLogsRequest):
    if not await db.is_record_correct(**log.model_dump()):
        raise HTTPException(status_code=400, detail="Invalid record")

    log_id = await db.insert_log_record(
        material_id=log.material_id,
        date=log.date,
        count=log.count,
    )

    return {"log_id": log_id}


@router.get("/materials-titles", response_model=schemas.ListMaterialsTitles)
async def list_materials_titles():
    items = await db.get_titles()
    return {
        "items": items,
    }


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
    from tracker.reading_log.routes import completion_info as get_completion_info

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
