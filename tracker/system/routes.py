from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import conint

from tracker.common.log import logger
from tracker.google_drive import main as drive_api
from tracker.reading_log import db as reading_log_db
from tracker.system import db


router = APIRouter(
    prefix="/system",
    tags=['system'],
    default_response_class=HTMLResponse
)
templates = Jinja2Templates(directory="templates")


@router.get('/',
            response_class=RedirectResponse)
async def system_view():
    redirect_path = router.url_path_for(graphic.__name__)
    material_id = await reading_log_db.get_material_reading_now()

    redirect_url = f"{redirect_path}?material_id={material_id}"
    return RedirectResponse(redirect_url, status_code=302)


@router.get('/graphic')
async def graphic(request: Request,
                  material_id: UUID | None = None,
                  last_days: conint(ge=1) = 7): # type: ignore
    context: dict[str, Any] = {
        'request': request,
    }

    if (material_id := material_id or await reading_log_db.get_material_reading_now()) is None:
        context['what'] = "No material found to show"
        return templates.TemplateResponse("errors/404.html", context)

    graphic_image = await db.create_reading_graphic(
        material_id=material_id,
        last_days=last_days
    )

    titles = await db.get_read_material_titles()

    context = {
        **context,
        'material_id': material_id,
        'last_days': last_days,
        'graphic_image': graphic_image,
        'titles': titles
    }

    return templates.TemplateResponse("graphic.html", context)


@router.get('/backup')
async def backup(request: Request):
    status = 'ok'
    try:
        await drive_api.backup()
    except Exception as e:
        logger.error("Backup error: %s", repr(e))
        status = 'backup-failed'

    context = {
        'request': request,
        'status': status
    }
    return templates.TemplateResponse("backup.html", context)


@router.get('/restore')
async def restore(request: Request):
    status = 'ok'
    try:
        await drive_api.restore()
    except Exception as e:
        logger.error("Restore error: %s", repr(e))
        status = 'restore-failed'

    context = {
        'request': request,
        'status': status
    }
    return templates.TemplateResponse("restore.html", context)
