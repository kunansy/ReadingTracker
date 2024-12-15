import asyncio
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, ORJSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import conint

from tracker.common.logger import logger
from tracker.google_drive import drive_api
from tracker.google_drive.db import get_tables_analytics
from tracker.system import db, schemas, trends


router = APIRouter(prefix="/system", tags=["system"], default_response_class=HTMLResponse)
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=RedirectResponse)
async def system_view():
    redirect_path = router.url_path_for(graphic.__name__)
    material_id = await db.get_material_reading_now()

    redirect_url = f"{redirect_path}?material_id={material_id}"
    return RedirectResponse(redirect_url, status_code=302)


@router.get("/graphics")
async def graphic(
    request: Request,
    material_id: UUID | None = None,
    last_days: conint(ge=1) = 7,  # type: ignore[valid-type]
):
    context: dict[str, Any] = {
        "request": request,
    }
    material_id = material_id or await db.get_material_reading_now()

    if material_id is None:
        context["what"] = "No material found to show"
        return templates.TemplateResponse("errors/404.html", context)

    async with asyncio.TaskGroup() as tg:
        reading_trend_task = tg.create_task(
            trends.get_span_reading_statistics(span_size=last_days),
        )
        notes_trend_task = tg.create_task(
            trends.get_span_notes_statistics(span_size=last_days),
        )
        completed_materials_trend_task = tg.create_task(
            trends.get_span_completed_materials_statistics(span_size=last_days),
        )
        repeated_materials_trend_task = tg.create_task(
            trends.get_span_repeated_materials_statistics(span_size=last_days),
        )
        tracker_statistics_task = tg.create_task(db.get_tracker_statistics())
        completion_dates_task = tg.create_task(db.get_completion_dates())
        titles_task = tg.create_task(db.get_read_material_titles())
        graphic_image_task = tg.create_task(
            db.create_reading_graphic(material_id=material_id, last_days=last_days),
        )

    reading_trend = reading_trend_task.result()
    notes_trend = notes_trend_task.result()
    completed_materials_trend = completed_materials_trend_task.result()
    repeated_materials_trend = repeated_materials_trend_task.result()
    completion_dates = completion_dates_task.result()

    notes_trend_graphic = trends.create_notes_graphic(notes_trend)
    reading_trend_graphic = trends.create_reading_graphic(
        reading_trend,
        completion_dates=completion_dates,
    )
    completed_materials_trend_graphic = trends.create_completed_materials_graphic(
        completed_materials_trend,
    )
    repeated_materials_trend_graphic = trends.create_repeated_materials_graphic(
        repeated_materials_trend,
    )

    context |= {
        "material_id": material_id,
        "last_days": last_days,
        "graphic_image": graphic_image_task.result(),
        "reading_trend": reading_trend,
        "notes_trend": notes_trend,
        "completed_materials_trend": completed_materials_trend,
        "repeated_materials_trend": repeated_materials_trend,
        "reading_trend_image": reading_trend_graphic,
        "notes_trend_image": notes_trend_graphic,
        "completed_materials_trend_image": completed_materials_trend_graphic,
        "repeated_materials_trend_image": repeated_materials_trend_graphic,
        "tracker_statistics": tracker_statistics_task.result(),
        "titles": titles_task.result(),
    }

    return templates.TemplateResponse("system/graphic.html", context)


@router.get("/backup")
async def backup(request: Request):
    async with asyncio.TaskGroup() as tg:
        tg.create_task(drive_api.backup())
        get_stat_task = tg.create_task(get_tables_analytics())

    context: dict[str, Any] = {"request": request, "status": "ok"}
    if stat := get_stat_task.result():
        context["materials_count"] = stat["materials"]
        context["logs_count"] = stat["reading_log"]
        context["statuses_count"] = stat["statuses"]
        context["notes_count"] = stat["notes"]
        context["cards_count"] = stat["cards"]
        context["repeats_count"] = stat["repeats"]
        context["repeats_history_count"] = stat["note_repeats_history"]

    return templates.TemplateResponse("system/backup.html", context)


@router.get("/restore")
async def restore(request: Request):
    status, snapshot_dict = "ok", None
    try:
        snapshot = await drive_api.restore()
        snapshot_dict = snapshot.to_dict()
    except Exception as e:
        logger.error("Restore error: %s", repr(e))
        status = "restore-failed"

    context: dict[str, Any] = {"request": request, "status": status}
    if snapshot_dict:
        context["materials_count"] = snapshot_dict["materials"].counter
        context["logs_count"] = snapshot_dict["reading_log"].counter
        context["statuses_count"] = snapshot_dict["statuses"].counter
        context["notes_count"] = snapshot_dict["notes"].counter

    return templates.TemplateResponse("system/restore.html", context)


@router.post(
    "/report",
    response_model=schemas.GetSpanReportResponse,
    response_class=ORJSONResponse,
)
async def get_span_report(span: schemas.GetSpanReportRequest):
    """Get analytics for the span: analyze materials, read items and inserted notes."""
    span_analysis = await trends.get_span_analytics(span)

    return {
        "completed_materials": span_analysis.materials_analytics.stats,
        "total_materials_completed": span_analysis.materials_analytics.total,
        "read_items": span_analysis.reading_analytics.stats,
        "reading": span_analysis.reading.dump(),
        "notes": span_analysis.notes.dump(),
        "repeats_total": span_analysis.repeat_analytics.repeats_count,
        "repeat_materials_count": span_analysis.repeat_analytics.unique_materials_count,
    }
