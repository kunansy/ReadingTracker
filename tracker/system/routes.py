from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from tracker.common.log import logger
from tracker.google_drive import drive_api


router = APIRouter(
    prefix="/system",
    tags=['system'],
    default_response_class=HTMLResponse
)
templates = Jinja2Templates(directory="templates")


@router.get('/')
async def system_view(request: Request):
    context = {
        'request': request,
        'is_ok': request.cookies.get('status')
    }
    return templates.TemplateResponse("system.html", context)


@router.get('/backup',
            response_class=RedirectResponse)
async def backup():
    response = RedirectResponse('/system', status_code=302)

    status = 'ok'
    try:
        await drive_api.backup()
    except Exception as e:
        logger.error("Backup error: %s", repr(e))
        status = 'backup-failed'

    response.set_cookie('status', status, expires=5)

    return response


@router.get('/restore',
            response_class=RedirectResponse)
async def restore():
    response = RedirectResponse('/system', status_code=302)

    status = 'ok'
    try:
        await drive_api.restore()
    except Exception as e:
        logger.error("Restore error: %s", repr(e))
        status = 'restore-failed'

    response.set_cookie('status', status, expires=5)

    return response
