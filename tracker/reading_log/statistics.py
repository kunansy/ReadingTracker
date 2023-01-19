import asyncio
import datetime
from typing import Any

import sqlalchemy.sql as sa

from tracker.common import database
from tracker.common.schemas import CustomBaseModel
from tracker.models import models
from tracker.reading_log import db


class LogStatistics(CustomBaseModel):
    material_id: str
    # total spent time including empty days
    total: int
    lost_time: int
    # days the material was being reading
    duration: int
    mean: int
    min_record: database.MinMax | None
    max_record: database.MinMax | None


async def get_m_log_statistics(*,
                               material_id: str,
                               logs: list[db.LogRecord] | None = None,
                               completion_dates: dict[str, datetime.datetime] | None = None) -> LogStatistics:
    """ Get material statistics from logs """
    async with asyncio.TaskGroup() as tg:
        if not logs:
            get_log_records_task = tg.create_task(db.get_log_records())
        else:
            get_log_records_task = tg.create_task(asyncio.sleep(1 / 1000, []))
        get_min_record_task = tg.create_task(_get_min_record(material_id=material_id))
        get_max_record_task = tg.create_task(_get_max_record(material_id=material_id))

    log_records = logs or get_log_records_task.result()
    duration = sum(
        1
        for log_record in log_records
        if log_record.material_id == material_id
    )
    total = lost_time = 0
    async for date, info in db.data(log_records=log_records, completion_dates=completion_dates):
        if material_id != info.material_id:
            continue
        total += info.count
        lost_time += info.count == 0

    return LogStatistics(
        material_id=material_id,
        total=total,
        lost_time=lost_time,
        duration=duration,
        mean=round(total / duration),
        min_record=get_min_record_task.result(),
        max_record=get_max_record_task.result()
    )


async def _get_start_date() -> datetime.date:
    stmt = sa.select(sa.func.min(models.ReadingLog.c.date))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def _get_last_date() -> datetime.date:
    stmt = sa.select(sa.func.max(models.ReadingLog.c.date))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def _get_log_duration() -> int:
    stmt = sa.select(sa.func.max(models.ReadingLog.c.date) -
                     sa.func.min(models.ReadingLog.c.date))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def _get_total_read_pages() -> int:
    stmt = sa.select(sa.func.sum(models.ReadingLog.count))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def _get_lost_days() -> int:
    stmt = sa.select(sa.func.max(models.ReadingLog.c.date) -
                     sa.func.min(models.ReadingLog.c.date) -
                     sa.func.count(1))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def get_mean_read_pages() -> int:
    stmt = sa.select(sa.func.avg(models.ReadingLog.c.count))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def _get_median_pages_read_per_day() -> int:
    stmt = sa.select(sa.func.median(models.ReadingLog.c.count))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def contains(*,
                   material_id: str) -> bool:
    stmt = sa.select(sa.func.count(1) >= 1) \
        .select_from(models.ReadingLog) \
        .where(models.ReadingLog.c.material_id == material_id)

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def _get_min_record(*,
                          material_id: str | None = None) -> database.MinMax | None:
    stmt = sa.select([models.ReadingLog,
                      models.Materials.c.title]) \
        .join(models.Materials,
              models.ReadingLog.c.material_id == models.Materials.c.material_id) \
        .order_by(models.ReadingLog.c.count) \
        .limit(1)

    if material_id:
        stmt = stmt \
            .where(models.ReadingLog.c.material_id == material_id)

    async with database.session() as ses:
        if minmax := (await ses.execute(stmt)).first():
            return database.MinMax(
                material_id=minmax.material_id,
                log_id=minmax.log_id,
                count=minmax.count,
                date=minmax.date,
                material_title=minmax.title
            )
    return None


async def _get_max_record(*,
                          material_id: str | None = None) -> database.MinMax | None:
    stmt = sa.select([models.ReadingLog,
                      models.Materials.c.title]) \
        .join(models.Materials,
              models.ReadingLog.c.material_id == models.Materials.c.material_id) \
        .order_by(models.ReadingLog.c.count.desc()) \
        .limit(1)

    if material_id:
        stmt = stmt \
            .where(models.ReadingLog.c.material_id == material_id)

    async with database.session() as ses:
        if minmax := (await ses.execute(stmt)).first():
            return database.MinMax(
                material_id=minmax.material_id,
                log_id=minmax.log_id,
                count=minmax.count,
                date=minmax.date,
                material_title=minmax.title
            )
    return None


async def _would_be_total() -> int:
    stmt = sa.select(sa.func.sum(models.ReadingLog.c.count) +
                     sa.func.avg(models.ReadingLog.c.count) * (
                             sa.func.max(models.ReadingLog.c.date) - # noqa
                             sa.func.min(models.ReadingLog.c.date) -
                             sa.func.count(1)))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def _get_total_materials_completed() -> int:
    stmt = sa.select(sa.func.count(1))\
        .where(models.Statuses.c.completed_at != None)

    async with database.session() as ses:
        return await ses.scalar(stmt)

async def get_log_statistics() -> dict[str, Any]:
    return {
        "start_date": await _get_start_date(),
        "stop_date": await _get_stop_date(),
        "duration": await _get_log_duration(),
        "lost_time": await _get_lost_days(),
        "average": await get_mean_read_pages(),
        "total_pages_read": await _get_total_read_pages(),
        "would_be_total": await _would_be_total(),
        "min": await _get_min_record(),
        "max": await _get_max_record(),
        "median": await _get_median_pages_read_per_day()
    }
