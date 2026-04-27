import asyncio
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from tracker.common import settings
from tracker.materials import db, schemas
from tracker.models import enums


router = APIRouter(prefix="/materials", tags=["materials-legacy"], deprecated=True)
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=RedirectResponse)
async def root():
    redirect_url = router.url_path_for(get_reading_materials.__name__)
    return RedirectResponse(redirect_url, status_code=302)


@router.get("/queue", response_class=HTMLResponse)
async def get_queue(request: Request):
    estimates = await db.estimate()
    mean = await db.get_means()

    context = {
        "request": request,
        "estimates": estimates,
        "mean": mean,
        "DATE_FORMAT": settings.DATE_FORMAT,
    }
    return templates.TemplateResponse(request, "materials/queue.html", context)


@router.get("/add-view", response_class=HTMLResponse)
async def insert_material_view(request: Request):
    """Insert a material to the queue."""
    async with asyncio.TaskGroup() as tg:
        get_tags_task = tg.create_task(db.get_material_tags())
        get_authors_task = tg.create_task(db.get_authors())

    context = {
        "request": request,
        "tags_list": get_tags_task.result(),
        "material_types": enums.MaterialTypesEnum,
        "material_authors": get_authors_task.result(),
    }
    return templates.TemplateResponse(request, "materials/add_material.html", context)


@router.get("/update-view", response_class=HTMLResponse)
async def update_material_view(
    request: Request,
    material_id: UUID,
    success: bool | None = None,  # noqa: FBT001
):
    context: dict[str, Any] = {
        "request": request,
    }

    if not (material := await db.get_material(material_id=material_id)):
        context["what"] = f"'{material_id=}' not found"
        return templates.TemplateResponse(request, "errors/404.html", context)

    tags = await db.get_material_tags()
    context = {
        **context,
        "material_id": material_id,
        "title": material.title,
        "authors": material.authors,
        "pages": material.pages,
        "material_type": material.material_type.name,
        "success": success,
        "material_types": enums.MaterialTypesEnum,
        "tags_list": tags,
    }
    if material.link:
        context["link"] = material.link
    if material.tags:
        context["tags"] = material.tags

    return templates.TemplateResponse(request, "materials/update_material.html", context)


@router.get("/reading", response_class=HTMLResponse)
async def get_reading_materials(request: Request):
    statistics = await db.reading_statistics()

    context = {
        "request": request,
        "statistics": statistics,
        "DATE_FORMAT": settings.DATE_FORMAT,
    }
    return templates.TemplateResponse(request, "materials/reading.html", context)


@router.get("/completed", response_class=HTMLResponse)
async def get_completed_materials(
    request: Request,
    search: Annotated[schemas.SearchParams, Depends()],
):
    async with asyncio.TaskGroup() as tg:
        get_statistics_task = tg.create_task(
            db.completed_statistics(
                material_type=search.get_material_type(),
                is_outlined=search.is_outlined,
                tags=search.requested_tags(),
            ),
        )
        get_material_tags_task = tg.create_task(db.get_material_tags())

    context = {
        "request": request,
        "statistics": get_statistics_task.result(),
        "tags": get_material_tags_task.result(),
        "material_tags": search.tags_query,
        "material_types": [item.value for item in enums.MaterialTypesEnum],
        "material_type": search.material_type,
        "outlined": search.outlined,
        "DATE_FORMAT": settings.DATE_FORMAT,
    }
    return templates.TemplateResponse(request, "materials/completed.html", context)


@router.get("/repeat-view", response_class=HTMLResponse)
async def get_repeat_view(request: Request, only_outlined: str = "off"):
    is_outlined = only_outlined == "on"
    repeating_queue = await db.get_repeating_queue(is_outlined=is_outlined)

    context = {
        "request": request,
        "repeating_queue": repeating_queue,
        "DATE_FORMAT": settings.DATE_FORMAT,
        "is_outlined": is_outlined,
    }
    return templates.TemplateResponse(request, "materials/repeat.html", context)
