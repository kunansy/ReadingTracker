from fastapi import APIRouter, Request

from tracker.common import settings
from tracker.reading_log import schemas, db


router = APIRouter(
    prefix="/reading-log",
    tags=["reading log"]
)


@router.get('/reading_log')
async def get_reading_log(request: Request):
    return {
        'request': request,
        'log': log.log,
        'DATE_FORMAT': settings.DATE_FORMAT,
        'EXPECTED_COUNT': settings.PAGES_PER_DAY
    }


@router.get('/reading_log/add')
async def add_log_record(request: Request):
    titles = tracker.get_material_titles(reading=True)
    reading_material_id = log.reading_material

    return {
        'request': request,
        'material_id': reading_material_id,
        'titles': titles,
        'date': trc.db.today()
    }


@router.post('/reading_log/add')
async def add_log_record(request: Request,
                         log_record: schemas.LogRecord):
    form_items = await get_form_items(request)

    try:
        record = validators.LogRecord(**form_items)
    except ValidationError as e:
        context = ujson.dumps(e.errors(), indent=4)
        sanic_logger.warning(f"Validation error:\n{context}")

        for error in e.errors():
            jinja.flash(request, f"{error['loc'][0]}: {error['msg']}", 'error')

        return response.redirect('/reading_log/add')

    try:
        log._set_log(**record.dict())
    except Exception:
        jinja.flash(request, str(e), 'error')
    else:
        jinja.flash(request, 'Record added', 'success')
    finally:
        return response.redirect('/reading_log/add')
