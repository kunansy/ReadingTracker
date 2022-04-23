import datetime
from typing import Any, NamedTuple
from uuid import UUID

import sqlalchemy.sql as sa

from tracker.common import database, models
from tracker.reading_log import db


class LogStatistics(NamedTuple):
    material_id: UUID
    # total spent time including empty days
    total: int
    lost_time: int
    # days the material was being reading
    duration: int
    average: int
    min_record: database.MinMax | None
    max_record: database.MinMax | None


async def get_m_log_statistics(*,
                               material_id: UUID) -> LogStatistics:
    """ Get material statistics from logs """
    duration = sum(
        1
        for _, info in (await db.get_log_records()).items()
        if info.material_id == material_id
    )
    total = lost_time = 0
    async for date, info in db.data():
        if material_id != info.material_id:
            continue
        total += info.count
        lost_time += info.count == 0

    min_record = await _get_min_record(material_id=material_id)
    max_record = await _get_max_record(material_id=material_id)

    return LogStatistics(
        material_id=material_id,
        total=total,
        lost_time=lost_time,
        duration=duration,
        average=round(total / duration),
        min_record=min_record,
        max_record=max_record
    )


async def _get_start_date() -> datetime.date:
    stmt = sa.select(sa.func.min(models.ReadingLog.c.date))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def _get_stop_date() -> datetime.date:
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


async def get_avg_read_pages() -> int:
    stmt = sa.select(sa.func.avg(models.ReadingLog.c.count))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def _get_median_pages_read_per_day() -> int:
    stmt = sa.select(sa.func.median(models.ReadingLog.c.count))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def contains(*,
                   material_id: UUID) -> bool:
    stmt = sa.select(sa.func.count(1) >= 1) \
        .select_from(models.ReadingLog) \
        .where(models.ReadingLog.c.material_id == str(material_id))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def _get_min_record(*,
                          material_id: UUID | None = None) -> database.MinMax | None:
    stmt = sa.select([models.ReadingLog,
                      models.Materials.c.title]) \
        .join(models.Materials,
              models.ReadingLog.c.material_id == models.Materials.c.material_id) \
        .order_by(models.ReadingLog.c.count) \
        .limit(1)

    if material_id:
        stmt = stmt \
            .where(models.ReadingLog.c.material_id == str(material_id))

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
                          material_id: UUID | None = None) -> database.MinMax | None:
    stmt = sa.select([models.ReadingLog,
                      models.Materials.c.title]) \
        .join(models.Materials,
              models.ReadingLog.c.material_id == models.Materials.c.material_id) \
        .order_by(models.ReadingLog.c.count.desc()) \
        .limit(1)

    if material_id:
        stmt = stmt \
            .where(models.ReadingLog.c.material_id == str(material_id))

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


async def get_log_statistics() -> dict[str, Any]:
    return {
        "start_date": await _get_start_date(),
        "stop_date": await _get_stop_date(),
        "duration": await _get_log_duration(),
        "lost_time": await _get_lost_days(),
        "average": await get_avg_read_pages(),
        "total_pages_read": await _get_total_read_pages(),
        "would_be_total": await _would_be_total(),
        "min": await _get_min_record(),
        "max": await _get_max_record(),
        "median": await _get_median_pages_read_per_day()
    }
