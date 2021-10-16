import datetime

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from tracker.common import settings
from tracker.reading_log import db, schemas


router = APIRouter(
    prefix="/reading_log",
    tags=["reading log"]
)
templates = Jinja2Templates(directory="templates")


@router.get('/')
async def get_reading_log(request: Request):
    reading_log = await db.get_log_records()

    context = {
        'request': request,
        'log': reading_log,
        'DATE_FORMAT': settings.DATE_FORMAT,
        'EXPECTED_COUNT': settings.PAGES_PER_DAY
    }
    return templates.TemplateResponse("reading_log.html", context)


@router.get('/add')
async def add_log_record_view(request: Request):
    titles = await db.get_material_titles()
    reading_material_id = await db.get_material_reading_now()
    today = datetime.datetime.utcnow()

    context = {
        'request': request,
        'material_id': reading_material_id,
        'titles': titles,
        'date': today
    }
    return templates.TemplateResponse("add_reading_log.html", context)


@router.post('/add')
async def add_log_record(log: schemas.LogRecord):
    await db.set_log(log=log)
    return RedirectResponse('/reading_log/add')
