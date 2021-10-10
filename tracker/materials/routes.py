from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from tracker.common import settings
from tracker.materials import db, schemas


router = APIRouter(
    prefix="materials/",
    tags=["materials"]
)


@router.get('/queue', response_class=HTMLResponse)
async def get_queue(request: Request):
    return {
        'request': request,
        'estimates': tracker.estimate(),
        'DATE_FORMAT': settings.DATE_FORMAT
    }


@router.get('/add', response_class=HTMLResponse)
async def add_material_view(request: Request):
    """ Add a material to the queue """
    return {
        'request': request,
        'title': request.ctx.session.get('title', ''),
        'authors': request.ctx.session.get('authors', ''),
        'pages': request.ctx.session.get('pages', ''),
        'tags': request.ctx.session.get('tags', ''),
    }


@router.post('/add', response_class=HTMLResponse)
async def add_material(request: Request,
                       material: schemas.Material):
    """ Add a material to the queue """
    form_items = await get_form_items(request)

    try:
        material = validators.Material(**form_items)
    except ValidationError as e:
        context = ujson.dumps(e.errors(), indent=4)
        sanic_logger.warning(f"Validation error:\n{context}")

        for error in e.errors():
            jinja.flash(request, f"{error['loc'][0]}: {error['msg']}", 'error')

        request.ctx.session.update(**form_items)
        return response.redirect('/materials/add')
    else:
        request.ctx.session.clear()

    tracker.add_material(**material.dict())
    jinja.flash(request, "Material added", 'success')

    return response.redirect('/materials/add')


@router.post('/start/{material_id}')
async def start_material(material_id: int):
    tracker.start_material(material_id)
    jinja.flash(request, f"Material {material_id=} started", 'success')

    return response.redirect('/materials/queue')


@router.post('/complete/{material_id}')
async def complete_material(material_id: int):
    tracker.complete_material(material_id)
    jinja.flash(request, f"Material {material_id=} completed", 'success')

    return response.redirect('/materials/reading')


@router.get('/reading', response_class=HTMLResponse)
async def get_reading_materials(request: Request):
    return {
        'request': request,
        'statistics': tracker.statistics(tracker.reading),
        'DATE_FORMAT': settings.DATE_FORMAT
    }


@router.get('/completed', response_class=HTMLResponse)
async def get_completed_materials(request: Request):
    return {
        'request': request,
        'statistics': tracker.statistics(tracker.processed),
        'DATE_FORMAT': settings.DATE_FORMAT
    }
