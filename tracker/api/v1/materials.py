import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import HttpUrl

from tracker.common import database
from tracker.common.logger import logger
from tracker.common.schemas import CustomBaseModel
from tracker.materials import db, schemas
from tracker.models import enums


router = APIRouter(prefix="/materials", tags=["materials-api"])


def _serialize_means(mean: enums.MEANS) -> dict[str, float]:
    return {k: float(v) for k, v in mean.items()}


class SwapOrderRequest(CustomBaseModel):
    material_id: UUID
    index: int


class OptionalStartBody(CustomBaseModel):
    started_at: datetime.date | None = None


class OptionalCompleteBody(CustomBaseModel):
    completed_at: datetime.date | None = None


class ParseLinkBody(CustomBaseModel):
    link: HttpUrl


@router.get("/queue")
async def get_queue_json():
    estimates = await db.estimate()
    mean = await db.get_means()
    return {
        "estimates": estimates,
        "mean": _serialize_means(mean),
    }


@router.get("/reading")
async def get_reading_json():
    statistics = await db.reading_statistics()
    return {
        "statistics": statistics,
    }


@router.get("/completed")
async def get_completed_json(search: Annotated[schemas.SearchParams, Depends()]):
    get_statistics = await db.completed_statistics(
        material_type=search.get_material_type(),
        is_outlined=search.is_outlined,
        tags=search.requested_tags(),
    )

    return {"statistics": get_statistics}


@router.get("/repeat")
async def get_repeat_json(*, only_outlined: bool = False):
    repeating_queue = await db.get_repeating_queue(is_outlined=only_outlined)
    return {
        "repeating_queue": repeating_queue,
        "is_outlined": only_outlined,
    }


@router.get("/authors")
async def get_authors():
    authors = await db.get_authors()

    return {
        "authors": authors,
    }


@router.get("/tags")
async def get_tags():
    tags = await db.get_material_tags()

    return {
        "tags": tags,
    }


@router.get("/queue/start")
async def queue_start_json():
    index = await db.get_queue_start()
    return {"index": index}


@router.get("/queue/end")
async def queue_end_json():
    index = await db.get_queue_end()
    return {"index": index}


@router.get("/is-reading")
async def is_reading_json(material_id: UUID):
    is_reading = await db.is_reading(material_id=material_id)
    return {"is_reading": is_reading}


@router.post("/parse/habr", response_model=schemas.ParsedMaterial)
async def parse_habr_json(payload: ParseLinkBody):
    link = payload.link
    if not (host := link.host):
        raise HTTPException(detail="Invalid habr url", status_code=400)

    if not (host.startswith("habr.") and host.endswith((".com", ".ru"))):
        raise HTTPException(detail="Invalid habr url", status_code=400)

    html = await db.get_html(str(link))
    article_info = db.parse_habr(html)

    return {
        "title": article_info.title,
        "authors": article_info.authors,
        "type": enums.MaterialTypesEnum.article,
        "link": link,
        "duration": None,
    }


@router.post("/parse/youtube", response_model=schemas.ParsedMaterial)
async def parse_youtube_json(payload: ParseLinkBody):
    link = payload.link
    if not (host := link.host):
        raise HTTPException(detail="Invalid youtube url", status_code=400)

    if host.replace("www.", "") not in ("youtube.com", "youtu.be"):
        raise HTTPException(detail="Invalid youtube url", status_code=400)

    if "youtube.com" in host:
        video_id = link.query_params()[0][1]
    else:
        video_id = (link.path or "").replace("/", "")

    try:
        video_info = await db.parse_youtube(video_id)
    except ValueError as e:
        logger.error("Failed to parse youtube, link=%s, e=%r", link, e)
        raise HTTPException(detail=str(e), status_code=400) from None

    return {
        "title": video_info.title,
        "authors": video_info.authors,
        "duration": video_info.duration,
        "type": enums.MaterialTypesEnum.lecture,
        # build a custom link to remove redundant query params
        "link": HttpUrl.build(
            scheme="https",
            host="youtube.com",
            path="watch",
            query=f"v={video_id}",
        ),
    }


@router.post("/", status_code=201)
async def create_material_json(material: schemas.Material):
    try:
        await db.insert_material(
            title=material.title,
            authors=material.authors,
            pages=material.pages,
            material_type=material.material_type,
            tags=material.tags,
            link=material.get_link(),
        )
    except database.AlreadyExistsException as e:
        logger.exception(e)
        msg = f"Material of type={material.material_type!r}, title={material.title!r} already exists"
        raise HTTPException(detail=msg, status_code=409) from None

    return {"ok": True}


@router.get("/{material_id}")
async def get_material_json(material_id: UUID):
    if not (material := await db.get_material(material_id=material_id)):
        raise HTTPException(status_code=404, detail="Material not found")

    return {"material": material}


@router.patch("/{material_id}")
async def update_material_json(material_id: UUID, body: schemas.UpdateMaterial):
    if material_id != body.material_id:
        raise HTTPException(status_code=400, detail="material_id mismatch")
    try:
        await db.update_material(
            material_id=body.material_id,
            title=body.title,
            authors=body.authors,
            pages=body.pages,
            material_type=body.material_type,
            tags=body.tags,
            link=body.get_link(),
        )
    except Exception as e:
        logger.error("Error updating material_id='%s': %s", body.material_id, repr(e))
        raise HTTPException(status_code=400, detail="Update failed") from e
    return {"ok": True}


@router.post("/{material_id}/start", status_code=204)
async def start_material_json(
    material_id: UUID,
    body: Annotated[OptionalStartBody | None, Body()] = None,
):
    started_at = body.started_at if body else None
    if not (material := await db.get_material(material_id=material_id)):
        raise HTTPException(status_code=404, detail=f"Material {material_id} not found")
    if material.index != (queue_start := await db.get_queue_start()):
        await db.swap_order(material_id, queue_start)

    await db.start_material(material_id=material_id, started_at=started_at)


@router.post("/{material_id}/complete", status_code=204)
async def complete_material_json(
    material_id: UUID,
    body: Annotated[OptionalCompleteBody | None, Body()] = None,
):
    completed_at = body.completed_at if body else None
    try:
        await db.complete_material(material_id=material_id, completed_at=completed_at)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{material_id}/outline", status_code=204)
async def outline_material_json(material_id: UUID):
    await db.outline_material(material_id=material_id)


@router.post("/{material_id}/repeat", status_code=204)
async def repeat_material_json(material_id: UUID):
    await db.repeat_material(material_id=material_id)


@router.post("/queue/swap-order", status_code=204)
async def swap_order_json(body: SwapOrderRequest):
    await db.swap_order(body.material_id, body.index)
