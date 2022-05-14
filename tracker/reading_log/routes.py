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
    reading_log = await db.get_log_records()

    context = {
        'request': request,
        'log': reading_log,
        'DATE_FORMAT': settings.DATE_FORMAT,
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
async def add_log_record(record: schemas.LogRecord = Depends()):
    await db.set_log(
        material_id=record.material_id,
        count=record.count,
        date=record.date
    )

    redirect_url = router.url_path_for(add_log_record_view.__name__)
    return RedirectResponse(redirect_url, status_code=302)
