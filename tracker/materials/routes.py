from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from tracker.common import settings
from tracker.common.log import logger
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


@router.get('/add', response_class=HTMLResponse)
async def add_material_view(request: Request):
    """ Add a material to the queue """
    context = {
        'request': request,
        'title': request.cookies.get('title', ''),
        'authors': request.cookies.get('authors', ''),
        'pages': request.cookies.get('pages', ''),
        'tags': request.cookies.get('tags', ''),
    }
    return templates.TemplateResponse("add_material.html", context)


@router.post('/add', response_class=HTMLResponse)
async def add_material(material: schemas.Material,
                       response: Response):
    """ Add a material to the queue """
    try:
        await db.add_material(material=material)
    except Exception:
        logger.exception("Error adding material")
        for key, value in material.dict().items():
            response.set_cookie(key=key, value=value)
    else:
        logger.debug("Material added")
        for key in material.dict().keys():
            response.delete_cookie(key=key)

    return RedirectResponse('/materials/add')


@router.post('/start/{material_id}')
async def start_material(material_id: int):
    await db.start_material(material_id=material_id)
    # jinja.flash(request, f"Material {material_id=} started", 'success')

    return RedirectResponse('/materials/queue')


@router.post('/complete/{material_id}')
async def complete_material(material_id: UUID):
    await db.complete_material(material_id=material_id)

    return RedirectResponse('/materials/reading')


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
    statistics = await db.processed_statistics()

    context = {
        'request': request,
        'statistics': statistics,
        'DATE_FORMAT': settings.DATE_FORMAT
    }
    return templates.TemplateResponse("completed.html", context)
