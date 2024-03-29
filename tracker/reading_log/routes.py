import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
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

    context = {
        "request": request,
        "material_id": log_material_id,
        "titles": get_titles.result(),
        "date": database.utcnow(),
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
