import datetime
from uuid import UUID

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import PositiveInt

from tracker.common import settings
from tracker.reading_log import db


router = APIRouter(
    prefix="/reading_log",
    tags=["reading log"],
    default_response_class=HTMLResponse
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


@router.get('/add-view')
async def add_log_record_view(request: Request):
    titles = await db.get_reading_material_titles()
    reading_material_id = await db.get_material_reading_now()
    today = datetime.datetime.utcnow()

    context = {
        'request': request,
        'material_id': reading_material_id,
        'titles': titles,
        'date': today
    }
    return templates.TemplateResponse("add_log_record.html", context)


@router.post('/add')
async def add_log_record(material_id: UUID = Form(...),
                         count: PositiveInt = Form(...),
                         date: datetime.date = Form(...)):
    await db.set_log(
        material_id=material_id, count=count, date=date)
    return RedirectResponse('/reading_log/add-view', status_code=302)
