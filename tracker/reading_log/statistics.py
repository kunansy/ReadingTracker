import asyncio
import datetime

import sqlalchemy.sql as sa

from tracker.common import database
from tracker.common.schemas import CustomBaseModel
from tracker.materials.db import _convert_duration_to_period
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


class TrackerStatistics(CustomBaseModel):
    # total tracker statistics
    started_at: datetime.date
    finished_at: datetime.date
    duration: int
    lost_time: int
    mean: float
    median: int
    total_pages_read: int
    total_materials_completed: int
    would_be_total: int
    min_log_record: database.MinMax | None
    max_log_record: database.MinMax | None

    @property
    def duration_period(self) -> str:
        return _convert_duration_to_period(self.duration)

    @property
    def lost_time_period(self) -> str:
        return _convert_duration_to_period(self.lost_time)

    @property
    def lost_time_percent(self) -> float:
        return round(self.lost_time / self.duration, 2) * 100

    @property
    def would_be_total_percent(self) -> float:
        """ How much would be total more than the
        current total pages count in percent """
        return round(self.would_be_total / self.total_pages_read, 2) * 100


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
        return (await ses.scalar(stmt)).date()


async def _get_last_date() -> datetime.date:
    stmt = sa.select(sa.func.max(models.ReadingLog.c.date))

    async with database.session() as ses:
        return (await ses.scalar(stmt)).date()


async def _get_log_duration() -> int:
    query = "EXTRACT('days' from max(date) - min(date)) + 1"
    stmt = sa.select(sa.text(query))\
        .select_from(models.ReadingLog)

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def _get_total_read_pages() -> int:
    stmt = sa.select(sa.func.sum(models.ReadingLog.c.count))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def _get_lost_days() -> int:
    query = "EXTRACT('days' from max(date) - min(date)) - count(1) + 1"
    stmt = sa.select(sa.text(query))\
        .select_from(models.ReadingLog)

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def get_mean_read_pages() -> int:
    stmt = sa.select(sa.func.avg(models.ReadingLog.c.count))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def _get_median_pages_read_per_day() -> int:
    stmt = sa.select(sa.text("PERCENTILE_CONT(0.5) WITHIN GROUP(ORDER BY count) AS median"))\
        .select_from(models.ReadingLog)

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
    query = "sum(count) + avg(count) * " \
            "(EXTRACT('days' from max(date) - min(date)) - count(1))"
    stmt = sa.select(sa.text(query))\
        .select_from(models.ReadingLog)

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def _get_total_materials_completed() -> int:
    stmt = sa.select(sa.func.count(1))\
        .where(models.Statuses.c.completed_at != None)

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def get_tracker_statistics() -> TrackerStatistics:
    async with asyncio.TaskGroup() as tg:
        started_at_task = tg.create_task(_get_start_date())
        finished_at_task = tg.create_task(_get_last_date())
        duration_task = tg.create_task(_get_log_duration())
        lost_time_task = tg.create_task(_get_lost_days())
        mean_task = tg.create_task(get_mean_read_pages())
        median_task = tg.create_task(_get_median_pages_read_per_day())
        total_pages_task = tg.create_task(_get_total_read_pages())
        total_materials_task = tg.create_task(_get_total_materials_completed())
        would_be_total_task = tg.create_task(_would_be_total())
        min_log_record_task = tg.create_task(_get_min_record())
        max_log_record_task = tg.create_task(_get_max_record())

    return TrackerStatistics(
        started_at=started_at_task.result(),
        finished_at=finished_at_task.result(),
        duration=duration_task.result(),
        lost_time=lost_time_task.result(),
        mean=round(mean_task.result(), 2),
        median=median_task.result(),
        total_pages_read=total_pages_task.result(),
        total_materials_completed=total_materials_task.result(),
        would_be_total=would_be_total_task.result(),
        min_log_record=min_log_record_task.result(),
        max_log_record=max_log_record_task.result()
    )
