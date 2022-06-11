from uuid import UUID

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from tracker.common import settings
from tracker.materials import db, schemas


router = APIRouter(
    prefix="/materials",
    tags=["materials"]
)
templates = Jinja2Templates(directory="templates")


@router.get('/queue', response_class=HTMLResponse)
async def get_queue(request: Request):
    estimates = await db.estimate()

    context = {
        'request': request,
        'estimates': estimates,
        'DATE_FORMAT': settings.DATE_FORMAT
    }
    return templates.TemplateResponse("queue.html", context)


@router.get('/add-view', response_class=HTMLResponse)
async def add_material_view(request: Request):
    """ Add a material to the queue """
    context = {
        'request': request,
    }
    return templates.TemplateResponse("add_material.html", context)


@router.post('/add', response_class=HTMLResponse)
async def add_material(material: schemas.Material = Depends()):
    """ Add a material to the queue """
    await db.add_material(
        title=material.title,
        authors=material.authors,
        pages=material.pages,
        tags=material.tags,
    )

    redirect_url = router.url_path_for(add_material_view.__name__)
    return RedirectResponse(redirect_url, status_code=302)


@router.post('/start/{material_id}')
async def start_material(material_id: UUID):
    await db.start_material(material_id=material_id)

    redirect_url = router.url_path_for(get_queue.__name__)
    return RedirectResponse(redirect_url, status_code=302)


@router.post('/complete/{material_id}')
async def complete_material(material_id: UUID):
    await db.complete_material(material_id=material_id)

    redirect_url = router.url_path_for(get_reading_materials.__name__)
    return RedirectResponse(redirect_url, status_code=302)


@router.post('/outline/{material_id}')
async def outline_material(material_id: UUID):
    """ Mark the material as outlined """
    await db.outline_material(material_id=material_id)

    redirect_url = router.url_path_for(get_reading_materials.__name__)
    return RedirectResponse(redirect_url, status_code=302)


@router.post('/repeat/{material_id}')
async def repeat_material(material_id: UUID):
    await db.repeat_material(material_id=material_id)

    redirect_url = router.url_path_for(get_repeating_queue.__name__)
    return RedirectResponse(redirect_url, status_code=302)


@router.get('/reading', response_class=HTMLResponse)
async def get_reading_materials(request: Request):
    statistics = await db.reading_statistics()

    context = {
        'request': request,
        'statistics': statistics,
        'DATE_FORMAT': settings.DATE_FORMAT
    }
    return templates.TemplateResponse("reading.html", context)


@router.get('/completed', response_class=HTMLResponse)
async def get_completed_materials(request: Request):
    statistics = await db.completed_statistics()

    context = {
        'request': request,
        'statistics': statistics,
        'DATE_FORMAT': settings.DATE_FORMAT
    }
    return templates.TemplateResponse("completed.html", context)


@router.get('/repeat-view', response_class=HTMLResponse)
async def get_repeating_queue(request: Request):
    repeating_queue = await db.get_repeating_queue()

    context = {
        'request': request,
        'repeating_queue': repeating_queue,
        'DATE_FORMAT': settings.DATE_FORMAT
    }
    return templates.TemplateResponse("repeat.html", context)
