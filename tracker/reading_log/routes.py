import asyncio
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, ORJSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from tracker.common import database, settings
from tracker.materials import db as materials_db
from tracker.reading_log import db, schemas


router = APIRouter(
    prefix="/reading_log",
    tags=["reading log"],
    default_response_class=HTMLResponse,
)
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def get_reading_log(request: Request, material_id: str | None = None):
    async with asyncio.TaskGroup() as tg:
        get_reading_logs = tg.create_task(db.get_log_records(material_id=material_id))
        get_mean_materials_read_pages = tg.create_task(db.get_mean_materials_read_pages())
        get_titles_task = tg.create_task(db.get_titles())

    context = {
        "request": request,
        "log": get_reading_logs.result(),
        "mean_materials_read_pages": get_mean_materials_read_pages.result(),
        "titles": get_titles_task.result(),
        "material_id": material_id or "",
        "DATE_FORMAT": settings.DATE_FORMAT,
    }
    return templates.TemplateResponse("reading_log/reading_log.html", context)


@router.get("/add-view")
async def add_log_record_view(request: Request, material_id: UUID | None = None):
    async with asyncio.TaskGroup() as tg:
        get_titles = tg.create_task(db.get_reading_material_titles())
        if material_id:
            is_material_reading = tg.create_task(
                materials_db.is_reading(material_id=material_id),
            )
        get_reading_material_id = tg.create_task(db.get_material_reading_now())

    log_material_id = material_id
    if not (material_id and is_material_reading.result()):
        log_material_id = get_reading_material_id.result()

    completion_info = await _completion_info(log_material_id)
    # here material must exist
    completion_info = cast(schemas.CompletionInfoSchema, completion_info)

    context = {
        "request": request,
        "material_id": log_material_id,
        "titles": get_titles.result(),
        "date": database.utcnow(),
        "pages_read": completion_info.pages_read,
        "material_pages": completion_info.material_pages,
    }
    return templates.TemplateResponse("reading_log/add_log_record.html", context)


@router.post("/add")
async def add_log_record(record: schemas.LogRecord = Depends()):
    if not await db.is_record_correct(**record.model_dump()):
        raise HTTPException(status_code=400, detail="Invalid record")

    await db.insert_log_record(
        material_id=str(record.material_id),
        count=record.count,
        date=record.date,
    )

    redirect_url = router.url_path_for(add_log_record_view.__name__)
    return RedirectResponse(redirect_url, status_code=302)


@router.get(
    "/completion-info",
    response_model=schemas.CompletionInfoSchema,
    response_class=ORJSONResponse,
)
async def get_completion_info(material_id: UUID):
    if completion_info := await _completion_info(material_id):
        return completion_info

    raise HTTPException(status_code=404, detail="Material not found")


async def _completion_info(
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
