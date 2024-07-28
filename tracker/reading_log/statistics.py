import asyncio
import datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

import sqlalchemy.sql as sa

from tracker.common import database
from tracker.common.schemas import CustomBaseModel
from tracker.materials.db import _convert_duration_to_period
from tracker.models import enums, models
from tracker.reading_log import db


class LogStatistics(CustomBaseModel):
    material_id: UUID
    # total spent time including empty days
    total: int
    lost_time: int
    # days the material was being reading
    duration: int
    min_record: database.MinMax | None = None
    max_record: database.MinMax | None = None

    @property
    def mean(self) -> int:
        return round(self.total / (self.duration or 1))


class TrackerStatistics(CustomBaseModel):
    # total tracker statistics
    started_at: datetime.date
    finished_at: datetime.date
    duration: int
    lost_time: int
    mean: float
    median: float
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
        return round(self.lost_time / self.duration * 100, 2)

    @property
    def would_be_total_percent(self) -> float:
        """How much would be total more than the current total pages count in percent."""
        return round(self.would_be_total / self.total_pages_read, 2) * 100


async def calculate_materials_stat(material_ids: set[UUID]) -> dict[UUID, LogStatistics]:
    """Get materials statistic from logs.

    Calculating several stats should reduce iteration over logs.data().
    """
    stat: dict[UUID, LogStatistics] = {}

    async for date, info in db.data():
        if (material_id := info.material_id) not in material_ids:
            continue
        if material_id not in stat:
            stat[material_id] = LogStatistics(
                material_id=material_id,
                total=0,
                lost_time=0,
                duration=0,
            )
        count = info.count
        row = stat[material_id]

        row.duration += count != 0
        row.lost_time += count == 0
        row.total += count
        if not (min_r := row.min_record) or min_r.count > count != 0:
            row.min_record = database.MinMax(date=date, count=count)
        if not (max_r := row.max_record) or max_r.count < count:
            row.max_record = database.MinMax(date=date, count=count)

    return stat


async def _get_start_date() -> datetime.date:
    stmt = sa.select(sa.func.min(models.ReadingLog.c.date))

    async with database.session() as ses:
        if res := await ses.scalar(stmt):
            return res
        raise ValueError(f"Table is empty, value is none: {res!r}")


async def _get_last_date() -> datetime.date:
    stmt = sa.select(sa.func.max(models.ReadingLog.c.date))

    async with database.session() as ses:
        if res := await ses.scalar(stmt):
            return res
        raise ValueError(f"Table is empty, value is none: {res!r}")


async def _get_log_duration() -> int:
    query = "max(date) - min(date) + 1"
    stmt = sa.select(sa.text(query)).select_from(models.ReadingLog)

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def _get_total_read_pages() -> int:
    stmt = sa.select(sa.func.sum(models.ReadingLog.c.count))

    async with database.session() as ses:
        return await ses.scalar(stmt) or 0


async def _get_lost_days() -> int:
    query = "max(date) - min(date) - count(1) + 1"
    stmt = sa.select(sa.text(query)).select_from(models.ReadingLog)

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def get_means() -> enums.MEANS:
    """Mean read pages, articles, seen lectures, listen audiobooks ect."""
    group = (
        sa.select(
            models.Materials.c.material_type,
            models.ReadingLog.c.date,
            sa.func.sum(models.ReadingLog.c.count).label("sum"),
        )
        .join(
            models.ReadingLog,
            models.ReadingLog.c.material_id == models.Materials.c.material_id,
        )
        .group_by(models.ReadingLog.c.date, models.Materials.c.material_type)
    ).cte("by_date")

    stmt = sa.select(
        group.c.material_type,
        sa.func.avg(group.c.sum).label("cnt"),
    ).group_by(group.c.material_type)

    async with database.session() as ses:
        return {
            row.material_type: round(row.cnt, 2)
            for row in (await ses.execute(stmt)).all()
        }


async def _get_median_pages_read_per_day() -> float:
    stmt = sa.select(
        sa.text("PERCENTILE_CONT(0.5) WITHIN GROUP(ORDER BY count) AS median"),
    ).select_from(models.ReadingLog)

    async with database.session() as ses:
        median = await ses.scalar(stmt)

    return round(float(median), 2)


async def contains(*, material_id: UUID) -> bool:
    stmt = (
        sa.select(sa.func.count(1) >= 1)  # type: ignore[arg-type]
        .select_from(models.ReadingLog)
        .where(models.ReadingLog.c.material_id == material_id)
    )

    async with database.session() as ses:
        return await ses.scalar(stmt) or False


async def _get_min_record(*, material_id: UUID | None = None) -> database.MinMax | None:
    stmt = (
        sa.select(models.ReadingLog, models.Materials.c.title)
        .join(models.Materials)
        .order_by(models.ReadingLog.c.count)
        .limit(1)
    )

    if material_id:
        stmt = stmt.where(models.ReadingLog.c.material_id == material_id)

    async with database.session() as ses:
        if minmax := (await ses.execute(stmt)).first():
            return database.MinMax(
                material_id=minmax.material_id,
                log_id=minmax.log_id,
                count=cast(int, minmax.count),
                date=minmax.date,
                material_title=minmax.title,
            )
    return None


async def _get_max_record(*, material_id: UUID | None = None) -> database.MinMax | None:
    stmt = (
        sa.select(models.ReadingLog, models.Materials.c.title)
        .join(models.Materials)
        .order_by(models.ReadingLog.c.count.desc())
        .limit(1)
    )

    if material_id:
        stmt = stmt.where(models.ReadingLog.c.material_id == material_id)

    async with database.session() as ses:
        if minmax := (await ses.execute(stmt)).first():
            return database.MinMax(
                material_id=minmax.material_id,
                log_id=minmax.log_id,
                count=cast(int, minmax.count),
                date=minmax.date,
                material_title=minmax.title,
            )
    return None


async def _would_be_total() -> int:
    query = "sum(count) + avg(count) * (max(date) - min(date) - count(1) + 1)"
    stmt = sa.select(sa.text(query)).select_from(models.ReadingLog)

    async with database.session() as ses:
        value = await ses.scalar(stmt)

    return round(value)


async def _get_total_materials_completed() -> int:
    stmt = sa.select(sa.func.count(1)).where(models.Statuses.c.completed_at != None)  # type: ignore[arg-type]

    async with database.session() as ses:
        return await ses.scalar(stmt) or 0


async def get_tracker_statistics() -> TrackerStatistics:
    async with asyncio.TaskGroup() as tg:
        started_at_task = tg.create_task(_get_start_date())
        finished_at_task = tg.create_task(_get_last_date())
        duration_task = tg.create_task(_get_log_duration())
        lost_time_task = tg.create_task(_get_lost_days())
        mean_task = tg.create_task(get_means())
        median_task = tg.create_task(_get_median_pages_read_per_day())
        total_pages_task = tg.create_task(_get_total_read_pages())
        total_materials_task = tg.create_task(_get_total_materials_completed())
        would_be_total_task = tg.create_task(_would_be_total())
        min_log_record_task = tg.create_task(_get_min_record())
        max_log_record_task = tg.create_task(_get_max_record())

    mean = mean_task.result().get(enums.MaterialTypesEnum.book, Decimal(1))

    return TrackerStatistics(
        started_at=started_at_task.result(),
        finished_at=finished_at_task.result(),
        duration=duration_task.result(),
        lost_time=lost_time_task.result(),
        mean=float(mean),
        median=median_task.result(),
        total_pages_read=total_pages_task.result(),
        total_materials_completed=total_materials_task.result(),
        would_be_total=would_be_total_task.result(),
        min_log_record=min_log_record_task.result(),
        max_log_record=max_log_record_task.result(),
    )
