import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import HttpUrl

from tracker.common.logger import logger
from tracker.materials import db, schemas
from tracker.models import enums


router = APIRouter(prefix="/materials", tags=["materials"])


@router.post("/add")
async def insert_material(material: Annotated[schemas.CreateMaterialRequest, Form()]):
    """Insert a material to the queue."""
    await db.insert_material(
        title=material.title,
        authors=material.authors,
        pages=material.pages,
        material_type=material.material_type,
        tags=material.tags,
        link=material.get_link(),
    )

    return RedirectResponse("/materials/add-view", status_code=302)


@router.post("/update", response_class=RedirectResponse)
async def update_material(material: Annotated[schemas.UpdateMaterialRequest, Form()]):
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

    redirect_url = (
        f"/materials/update-view?material_id={material.material_id}&success={success}"
    )

    return RedirectResponse(redirect_url, status_code=302)


@router.post("/start/{material_id}")
async def start_material(material_id: UUID, started_at: datetime.date | None = None):
    if not (material := await db.get_material(material_id=material_id)):
        raise HTTPException(status_code=404, detail=f"Material {material_id} not found")
    if material.index != (queue_start := await db.get_queue_start()):
        await db.swap_order(material_id, queue_start)

    await db.start_material(material_id=material_id, started_at=started_at)

    return RedirectResponse("/materials/reading", status_code=302)


@router.post("/complete/{material_id}")
async def complete_material(material_id: UUID, completed_at: datetime.date | None = None):
    await db.complete_material(material_id=material_id, completed_at=completed_at)


@router.post("/outline/{material_id}")
async def outline_material(material_id: UUID):
    """Mark the material as outlined."""
    await db.outline_material(material_id=material_id)

    return RedirectResponse("/materials/reading", status_code=302)


@router.post("/repeat/{material_id}")
async def repeat_material(material_id: UUID, is_outlined: bool | None = None):  # noqa: FBT001
    await db.repeat_material(material_id=material_id)

    only_outlined = "on" if is_outlined else "off"

    return RedirectResponse(
        f"/materials/repeat-view?only_outlined={only_outlined}",
        status_code=302,
    )


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

    return RedirectResponse("/materials/queue", status_code=302)


@router.get("/is-reading")
async def is_material_reading(material_id: UUID):
    is_reading = await db.is_reading(material_id=material_id)

    return {"is_reading": is_reading}


@router.post(
    "/parse/habr",
    response_model=schemas.ParsedMaterialResponse,
    response_model_exclude_unset=True,
)
async def parse_habr_article(link: HttpUrl):
    if not (host := link.host):
        raise HTTPException(detail="Invalid habr url", status_code=400)

    if not (host.startswith("habr.") and host.endswith((".com", ".ru"))):
        raise HTTPException(detail="Invalid habr url", status_code=400)

    html = await db.get_html(str(link))
    article_info = db.parse_habr(html)

    return schemas.ParsedMaterialResponse(
        title=article_info.title,
        authors=article_info.authors,
        type=enums.MaterialTypesEnum.article,
        link=link,
        duration=None,
    )


@router.post(
    "/parse/youtube",
    response_model=schemas.ParsedMaterialResponse,
    response_model_exclude_unset=True,
)
async def parse_youtube_video(link: HttpUrl):
    if not (host := link.host):
        raise HTTPException(detail="Invalid youtube url", status_code=400)

    if host.replace("www.", "") not in ("youtube.com", "youtu.be"):
        raise HTTPException(detail="Invalid youtube url", status_code=400)

    video_id = link.query_params()[0][1]
    video_info = await db.parse_youtube(video_id)

    return schemas.ParsedMaterialResponse(
        title=video_info.title,
        authors=video_info.authors,
        duration=video_info.duration,
        type=enums.MaterialTypesEnum.lecture,
        link=link,
    )
