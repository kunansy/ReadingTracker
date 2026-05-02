import asyncio
from typing import Annotated

from fastapi import APIRouter
from fastapi.params import Depends
from fastapi.responses import JSONResponse

from tracker.google_drive import (
    db as drive_db,
    drive_api,
)
from tracker.reading_log import (
    db as logs_db,
    statistics,
)
from tracker.system import db, schemas, trends


router = APIRouter(prefix="/system", tags=["system-api"])


@router.get("/meta", response_class=JSONResponse)
async def system_meta():
    async with asyncio.TaskGroup() as tg:
        titles_task = tg.create_task(db.get_read_material_titles())
        reading_now_task = tg.create_task(logs_db.get_material_reading_now())

    return {
        "material_id": reading_now_task.result(),
        "titles": titles_task.result(),
    }


@router.get("/summary", response_model=schemas.GetSystemSummaryResponse)
async def get_system_summary(r: Annotated[schemas.GetSystemSummaryRequest, Depends()]):
    last_days = r.last_days

    async with asyncio.TaskGroup() as tg:
        tracker_statistics_task = tg.create_task(statistics.get_tracker_statistics())

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
        outlined_materials_trend_task = tg.create_task(
            trends.get_span_outlined_materials_statistics(span_size=last_days),
        )

    return {
        "tracker_statistics": tracker_statistics_task.result(),
        "reading_trend": reading_trend_task.result(),
        "notes_trend": notes_trend_task.result(),
        "completed_materials_trend": completed_materials_trend_task.result(),
        "repeated_materials_trend": repeated_materials_trend_task.result(),
        "outlined_materials_trend": outlined_materials_trend_task.result(),
    }


@router.get("/graphics/reading-progress", response_model=schemas.GetImageResponse)
async def graphic_reading_progress(
    r: Annotated[schemas.GetReadingProgressGraphicRequest, Depends()],
):
    image = await db.create_reading_graphic(
        material_id=r.material_id,
        last_days=r.last_days,
    )

    return {"image": image}


@router.get("/graphics/outline-percentage", response_model=schemas.GetImageResponse)
async def graphic_outline_percentage():
    image = await db.create_outline_percentage_graphic()
    return {"image": image}


@router.get("/graphics/reading-trend", response_model=schemas.GetImageResponse)
async def graphic_reading_trend(
    r: Annotated[schemas.GetReadingTrendGraphicRequest, Depends()],
):
    async with asyncio.TaskGroup() as tg:
        stat_task = tg.create_task(
            trends.get_span_reading_statistics(span_size=r.last_days),
        )
        completion_dates_task = tg.create_task(logs_db.get_completion_dates())
    image = trends.create_reading_graphic(
        stat_task.result(),
        completion_dates=completion_dates_task.result(),
    )

    return {"image": image}


@router.get("/graphics/notes-trend", response_model=schemas.GetImageResponse)
async def graphic_notes_trend(
    r: Annotated[schemas.GetNotesTrendGraphicRequest, Depends()],
):
    stat = await trends.get_span_notes_statistics(span_size=r.last_days)

    return {"image": trends.create_notes_graphic(stat)}


@router.get(
    "/graphics/completed-materials-trend",
    response_model=schemas.GetImageResponse,
)
async def graphic_completed_materials_trend(
    r: Annotated[schemas.GetCompletedMaterialsTrendGraphicRequest, Depends()],
):
    stat = await trends.get_span_completed_materials_statistics(span_size=r.last_days)

    return {"image": trends.create_completed_materials_graphic(stat)}


@router.get("/graphics/repeated-materials-trend", response_model=schemas.GetImageResponse)
async def graphic_repeated_materials_trend(
    r: Annotated[schemas.GetRepeatedMaterialsTrendGraphicRequest, Depends()],
):
    stat = await trends.get_span_repeated_materials_statistics(span_size=r.last_days)

    return {"image": trends.create_repeated_materials_graphic(stat)}


@router.get("/graphics/outlined-materials-trend", response_model=schemas.GetImageResponse)
async def graphic_outlined_materials_trend(
    r: Annotated[schemas.GetOutlinedMaterialsTrendGraphicRequest, Depends()],
):
    stat = await trends.get_span_outlined_materials_statistics(span_size=r.last_days)

    return {"image": trends.create_outlined_materials_graphic(stat)}


@router.get("/graphics/total-read", response_model=schemas.GetImageResponse)
async def graphic_total_read(r: Annotated[schemas.GetTotalReadGraphicRequest, Depends()]):
    stat = await trends.get_span_total_read_statistics(span_size=r.last_days)

    return {"image": trends.create_total_read_graphic(stat)}


@router.post("/backup", response_model=schemas.BackupResponse)
async def backup_api():
    async with asyncio.TaskGroup() as tg:
        tg.create_task(drive_api.backup())
        get_stat_task = tg.create_task(drive_db.get_tables_analytics())

    stat = get_stat_task.result()
    return schemas.BackupResponse(
        materials_count=stat["materials_count"],
        reading_log_count=stat["reading_log_count"],
        statuses_count=stat["statuses_count"],
        notes_count=stat["notes_count"],
        cards_count=stat["cards_count"],
        repeats_count=stat["repeats_count"],
        note_repeats_history_count=stat["note_repeats_history_count"],
    )


@router.post("/restore", response_model=schemas.RestoreResponse)
async def restore_api():
    snapshot = await drive_api.restore()

    snapshot_dict = snapshot.to_dict()
    return schemas.RestoreResponse(
        materials_count=snapshot_dict["materials"].counter,
        reading_log_count=snapshot_dict["reading_log"].counter,
        statuses_count=snapshot_dict["statuses"].counter,
        notes_count=snapshot_dict["notes"].counter,
        cards_count=snapshot_dict["cards"].counter,
        repeats_count=snapshot_dict["repeats"].counter,
        note_repeats_history_count=snapshot_dict["note_repeats_history"].counter,
    )
