import asyncio
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import HttpUrl

from tracker.common import settings
from tracker.common.logger import logger
from tracker.materials import db, schemas
from tracker.models import enums


router = APIRouter(prefix="/materials", tags=["materials"])
# could not specify the directory as 'templates/materials',
# because templates contains references to the root templates folder
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
    return templates.TemplateResponse("materials/queue.html", context)


@router.get("/add-view", response_class=HTMLResponse)
async def insert_material_view(request: Request):
    """Insert a material to the queue."""
    tags = await db.get_material_tags()
    context = {
        "request": request,
        "tags_list": tags,
        "material_types": enums.MaterialTypesEnum,
    }
    return templates.TemplateResponse("materials/add_material.html", context)


@router.post("/add", response_class=HTMLResponse)
async def insert_material(material: Annotated[schemas.Material, Depends()]):
    """Insert a material to the queue."""
    await db.insert_material(
        title=material.title,
        authors=material.authors,
        pages=material.pages,
        material_type=material.material_type,
        tags=material.tags,
        link=material.get_link(),
    )

    redirect_url = router.url_path_for(insert_material_view.__name__)
    return RedirectResponse(redirect_url, status_code=302)


@router.get("/update-view", response_class=HTMLResponse)
async def update_material_view(
    request: Request,
    material_id: UUID,
    success: bool | None = None,
):
    context: dict[str, Any] = {
        "request": request,
    }

    if not (material := await db.get_material(material_id=material_id)):
        context["what"] = f"'{material_id=}' not found"
        return templates.TemplateResponse("errors/404.html", context)

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

    return templates.TemplateResponse("materials/update_material.html", context)


@router.post("/update", response_class=RedirectResponse)
async def update_material(material: Annotated[schemas.UpdateMaterial, Depends()]):
    success = True
    try:
        await db.update_material(
            material_id=material.material_id,
            title=material.title,
            authors=material.authors,
            pages=material.pages,
            material_type=material.material_type,
            tags=material.tags,
            link=material.get_link(),
        )
    except Exception as e:
        logger.error("Error updating material_id='%s': %s", material.material_id, repr(e))
        success = False

    redirect_path = router.url_path_for(update_material_view.__name__)
    redirect_url = f"{redirect_path}?material_id={material.material_id}&{success=}"

    return RedirectResponse(redirect_url, status_code=302)


@router.post("/start/{material_id}")
async def start_material(material_id: UUID):
    if not (material := await db.get_material(material_id=material_id)):
        raise HTTPException(status_code=404, detail=f"Material {material_id} not found")
    # don't shift queue if the material is the first item
    if material.index != (queue_start := await db.get_queue_start()):
        await db.swap_order(material_id, queue_start)

    await db.start_material(material_id=material_id)

    redirect_url = router.url_path_for(get_reading_materials.__name__)
    return RedirectResponse(redirect_url, status_code=302)


@router.post("/complete/{material_id}")
async def complete_material(material_id: UUID):
    await db.complete_material(material_id=material_id)

    redirect_url = router.url_path_for(get_completed_materials.__name__)
    return RedirectResponse(redirect_url, status_code=302)


@router.post("/outline/{material_id}")
async def outline_material(material_id: UUID):
    """Mark the material as outlined."""
    await db.outline_material(material_id=material_id)

    redirect_url = router.url_path_for(get_reading_materials.__name__)
    return RedirectResponse(redirect_url, status_code=302)


@router.post("/repeat/{material_id}")
async def repeat_material(material_id: UUID, is_outlined: bool | None = None):
    await db.repeat_material(material_id=material_id)

    only_outlined = "on" if is_outlined else "off"

    redirect_url = router.url_path_for(get_repeat_view.__name__).__str__()
    redirect_url = f"{redirect_url}?only_outlined={only_outlined}"
    return RedirectResponse(redirect_url, status_code=302)


@router.get("/reading", response_class=HTMLResponse)
async def get_reading_materials(request: Request):
    statistics = await db.reading_statistics()

    context = {
        "request": request,
        "statistics": statistics,
        "DATE_FORMAT": settings.DATE_FORMAT,
    }
    return templates.TemplateResponse("materials/reading.html", context)


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
    return templates.TemplateResponse("materials/completed.html", context)


@router.get("/repeat-view", response_class=HTMLResponse)
async def get_repeat_view(request: Request, only_outlined: Literal["on", "off"] = "off"):
    is_outlined = only_outlined == "on"
    repeating_queue = await db.get_repeating_queue(is_outlined=is_outlined)

    context = {
        "request": request,
        "repeating_queue": repeating_queue,
        "DATE_FORMAT": settings.DATE_FORMAT,
        "is_outlined": is_outlined,
    }
    return templates.TemplateResponse("materials/repeat.html", context)


@router.get("/repeat-queue", response_model=list[db.RepeatingQueue])
async def get_repeat_queue(*, only_outlined: bool = False):
    return await db.get_repeating_queue(is_outlined=only_outlined)


@router.get("/queue/start")
async def get_queue_start():
    """Get the first material index in the queue."""
    index = await db.get_queue_start()

    return {"index": index}


@router.get("/queue/end")
async def get_queue_end():
    """Get the last material index in the queue."""
    index = await db.get_queue_end()

    return {"index": index}


@router.post("/queue/swap-order", response_class=RedirectResponse)
async def update_queue_order(material_id: UUID, index: int):
    await db.swap_order(material_id, index)

    redirect_url = router.url_path_for(get_queue.__name__)
    return RedirectResponse(redirect_url, status_code=302)


@router.get("/is-reading")
async def is_material_reading(material_id: UUID):
    is_reading = await db.is_reading(material_id=material_id)

    return {"is_reading": is_reading}


@router.post(
    "/parse/habr",
    response_model=schemas.ParsedMaterial,
    response_model_exclude_unset=True,
)
async def parse_habr_article(link: HttpUrl):
    if not (host := link.host):
        return HTTPException(detail="Invalid habr url", status_code=400)

    if not (host.startswith("habr.") and host.endswith((".com", ".ru"))):
        return HTTPException(detail="Invalid habr url", status_code=400)

    html = await db.get_html(str(link))
    article_info = db.parse_habr(html)

    return {"link": str(link), "type": "article", **article_info}


@router.post(
    "/parse/youtube",
    response_model=schemas.ParsedMaterial,
    response_model_exclude_unset=True,
)
async def parse_youtube_video(link: HttpUrl):
    if not (host := link.host):
        return HTTPException(detail="Invalid youtube url", status_code=400)

    if host.replace("www.", "") not in ("youtube.com", "youtu.be"):
        return HTTPException(detail="Invalid youtube url", status_code=400)

    video_id = link.query_params()[0][1]
    video_info = await db.parse_youtube(video_id)

    return {"link": str(link), "type": "lecture", **video_info}
