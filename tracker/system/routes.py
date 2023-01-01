import asyncio
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import conint

from tracker.common.log import logger
from tracker.google_drive import main as drive_api
from tracker.system import db, trends

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
    material_id = await db.get_material_reading_now()

    redirect_url = f"{redirect_path}?material_id={material_id}"
    return RedirectResponse(redirect_url, status_code=302)


@router.get('/graphics')
async def graphic(request: Request,
                  material_id: UUID | None = None,
                  last_days: conint(ge=1) = 7): # type: ignore
    context: dict[str, Any] = {
        'request': request,
    }
    if material_id:
        material_id_: str | None = str(material_id)
    else:
        material_id_ = await db.get_material_reading_now()

    if material_id_ is None:
        context['what'] = "No material found to show"
        return templates.TemplateResponse("errors/404.html", context)

    async with asyncio.TaskGroup() as tg:
        reading_trend_task = tg.create_task(trends.get_week_reading_statistics())
        notes_trend_task = tg.create_task(trends.get_week_notes_statistics())

    reading_trend = reading_trend_task.result()
    notes_trend = notes_trend_task.result()

    graphic_image_task = asyncio.create_task(db.create_reading_graphic(
        material_id=material_id_,
        last_days=last_days
    ))
    reading_trend_graphic_task = asyncio.create_task(
        trends.create_reading_graphic(reading_trend))
    notes_trend_graphic_task = asyncio.create_task(
        trends.create_notes_graphic(notes_trend))
    titles_task = asyncio.create_task(
        db.get_read_material_titles())

    await graphic_image_task
    await reading_trend_graphic_task
    await notes_trend_graphic_task
    await titles_task

    context = {
        **context,
        'material_id': material_id,
        'last_days': last_days,
        'graphic_image': graphic_image_task.result(),
        'reading_trend': reading_trend,
        'notes_trend': notes_trend,
        'reading_trend_image': reading_trend_graphic_task.result(),
        'notes_trend_image': notes_trend_graphic_task.result(),
        'titles': titles_task.result()
    }

    return templates.TemplateResponse("system/graphic.html", context)


@router.get('/backup')
async def backup(request: Request):
    status, snapshot_dict = 'ok', None
    try:
        snapshot = await drive_api.backup()
        snapshot_dict = snapshot.to_dict()
    except Exception as e:
        logger.error("Backup error: %s", repr(e))
        status = 'backup-failed'

    context: dict[str, Any] = {
        'request': request,
        'status': status
    }
    if snapshot_dict:
        context['materials_count'] = snapshot_dict['materials'].counter
        context['logs_count'] = snapshot_dict['reading_log'].counter
        context['statuses_count'] = snapshot_dict['statuses'].counter
        context['notes_count'] = snapshot_dict['notes'].counter

    return templates.TemplateResponse("system/backup.html", context)


@router.get('/restore')
async def restore(request: Request):
    status, snapshot_dict = 'ok', None
    try:
        snapshot = await drive_api.restore()
        snapshot_dict = snapshot.to_dict()
    except Exception as e:
        logger.error("Restore error: %s", repr(e))
        status = 'restore-failed'

    context: dict[str, Any] = {
        'request': request,
        'status': status
    }
    if snapshot_dict:
        context['materials_count'] = snapshot_dict['materials'].counter
        context['logs_count'] = snapshot_dict['reading_log'].counter
        context['statuses_count'] = snapshot_dict['statuses'].counter
        context['notes_count'] = snapshot_dict['notes'].counter

    return templates.TemplateResponse("system/restore.html", context)
