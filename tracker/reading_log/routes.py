import asyncio
import datetime

from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from tracker.common import settings
from tracker.reading_log import db, schemas


router = APIRouter(
    prefix="/reading_log",
    tags=["reading log"],
    default_response_class=HTMLResponse
)
templates = Jinja2Templates(directory="templates")


@router.get('/')
async def get_reading_log(request: Request):
    get_reading_logs = asyncio.create_task(db.get_log_records())
    get_average_materials_read_pages = asyncio.create_task(
        db.get_average_materials_read_pages())

    await asyncio.gather(
        get_reading_logs,
        get_average_materials_read_pages
    )

    context = {
        'request': request,
        'log': get_reading_logs.result(),
        'average_materials_read_pages': get_average_materials_read_pages.result(),
        'DATE_FORMAT': settings.DATE_FORMAT,
    }
    return templates.TemplateResponse("reading_log/reading_log.html", context)


@router.get('/add-view')
async def add_log_record_view(request: Request):
    get_titles = asyncio.create_task(db.get_reading_material_titles())
    get_reading_material_id = asyncio.create_task(db.get_material_reading_now())
    today = datetime.datetime.utcnow()

    await asyncio.gather(
        get_titles,
        get_reading_material_id
    )

    context = {
        'request': request,
        'material_id': get_reading_material_id.result(),
        'titles': get_titles.result(),
        'date': today
    }
    return templates.TemplateResponse("reading_log/add_log_record.html", context)


@router.post('/add')
async def add_log_record(record: schemas.LogRecord = Depends()):
    await db.set_log(
        material_id=record.material_id,
        count=record.count,
        date=record.date
    )

    redirect_url = router.url_path_for(add_log_record_view.__name__)
    return RedirectResponse(redirect_url, status_code=302)
