import datetime
from typing import Any, AsyncGenerator, NamedTuple, Optional
from uuid import UUID

import sqlalchemy.sql as sa
from sqlalchemy.engine import RowMapping

from tracker.common import database, models
from tracker.common.log import logger
from tracker.reading_log import schemas


class LogRecord(NamedTuple):
    count: int # type: ignore
    material_id: UUID
    material_title: Optional[str] = None


class MaterialStatistics(NamedTuple):
    material_id: UUID
    # total spent time including empty days
    total: int
    lost_time: int
    # days the material was being reading
    duration: int
    average: int


def safe_list_get(list_: list[Any],
                  index: int,
                  default: Any = None) -> Any:
    try:
        return list_[index]
    except IndexError:
        return default


async def get_log_records() -> dict[datetime.date, RowMapping]:
    logger.debug("Getting all log records")

    stmt = sa.select([models.ReadingLog,
                      models.Materials.c.title.label('material_title')])\
        .join(models.Materials,
              models.Materials.c.material_id == models.ReadingLog.c.material_id)

    async with database.session() as ses:
        return {
            row.date: row
            async for row in await ses.stream(stmt)
        }


async def get_material_titles() -> dict[UUID, str]:
    return await database.get_material_titles()


async def data() -> AsyncGenerator[tuple[datetime.date, LogRecord], None]:
    """ Get pairs: (date, info) of all days from start to stop.

    If the day is empty, material_id is supposed
    as the material_id of the last not empty day.
    """
    logger.debug("Getting data from log")

    if not (log_records := await get_log_records()):
        return

    # stack for materials
    materials: list[UUID] = []
    try:
        completion_dates = await database.get_completion_dates()
    except Exception as e:
        logger.exception(e)
        completion_dates = {}

    step = datetime.timedelta(days=1)
    iter_over_dates = min(log_records.keys())

    while iter_over_dates <= database.today().date():
        last_material_id = safe_list_get(materials, -1, None)

        if ((completion_date := completion_dates.get(last_material_id))
                and completion_date < iter_over_dates):
            materials.pop()
            last_material_id = safe_list_get(materials, -1, None)

        if not (info := log_records.get(iter_over_dates)):
            info = LogRecord(material_id=last_material_id, count=0)
        else:
            material_id = info.material_id

            if not (materials and material_id in materials):
                # new material started, the last one completed
                materials += [material_id]
            elif material_id != last_material_id:
                # in this case several materials
                # are being reading one by one
                materials.remove(material_id)
                materials += [material_id]

        yield iter_over_dates, info
        iter_over_dates += step


async def get_material_statistics(*,
                                  material_id: UUID) -> MaterialStatistics:
    duration = sum(
        1
        for _, info in await get_log_records()
        if info.material_id == material_id
    )
    total = lost_time = 0
    async for date, info in data():
        if material_id != info.material_id:
            continue
        total += 1
        lost_time += info.count == 0

    return MaterialStatistics(
        material_id=material_id,
        total=total,
        lost_time=lost_time,
        duration=duration,
        average=round(total / duration)
    )


async def get_start_date() -> datetime.date:
    stmt = sa.select(sa.func.min(models.ReadingLog.c.date))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def get_stop_date() -> datetime.date:
    stmt = sa.select(sa.func.max(models.ReadingLog.c.date))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def get_log_duration() -> int:
    stmt = sa.select(sa.func.max(models.ReadingLog.c.date) -
                     sa.func.min(models.ReadingLog.c.date))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def get_total_read_pages() -> int:
    stmt = sa.select(sa.func.sum(models.ReadingLog.count))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def get_lost_days() -> int:
    stmt = sa.select(sa.func.max(models.ReadingLog.c.date) -
                     sa.func.min(models.ReadingLog.c.date) -
                     sa.func.count(1))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def get_average_pages_read_per_day() -> int:
    stmt = sa.select(sa.func.avg(models.ReadingLog.count))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def get_median_pages_read_per_day() -> int:
    stmt = sa.select(sa.func.median(models.ReadingLog.count))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def contains(*,
                   material_id: UUID) -> bool:
    stmt = sa.select(sa.func.count(1) >= 1)\
        .select_from(models.ReadingLog)\
        .where(models.ReadingLog.c.material_id == str(material_id))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def get_min_record() -> Optional[RowMapping]:
    stmt = sa.select([models.ReadingLog,
                      models.Materials.c.title])\
        .join(models.Materials,
              models.ReadingLog.c.material_id == models.Materials.c.material_id) \
        .order_by(models.ReadingLog.c.count)\
        .limit(1)

    async with database.session() as ses:
        return (await ses.execute(stmt)).first()


async def get_max_record() -> Optional[RowMapping]:
    stmt = sa.select([models.ReadingLog,
                      models.Materials.c.title]) \
        .join(models.Materials,
              models.ReadingLog.c.material_id == models.Materials.c.material_id) \
        .order_by(models.ReadingLog.c.count.desc()) \
        .limit(1)

    async with database.session() as ses:
        return (await ses.execute(stmt)).first()


async def would_be_total() -> int:
    stmt = sa.select(sa.func.sum(models.ReadingLog.c.count) +
                     sa.func.avg(models.ReadingLog.c.count) * (
                     sa.func.max(models.ReadingLog.c.date) -
                     sa.func.min(models.ReadingLog.c.date) -
                     sa.func.count(1)))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def get_log_statistics():
    return {
        "start_date": await get_start_date(),
        "stop_date": await get_stop_date(),
        "duration": await get_log_duration(),
        "lost_time": await get_lost_days(),
        "average": await get_average_pages_read_per_day(),
        "total_pages_read": await get_total_read_pages(),
        "would_be_total": await would_be_total(),
        "min": await get_min_record(),
        "max": await get_max_record(),
        "median": await get_median_pages_read_per_day()
    }


async def get_material_reading_now() -> Optional[UUID]:
    if not await get_log_records():
        logger.warning("Reading log is empty, no materials reading")
        return # type: ignore

    last_material_id = None
    async for _, info in data():
        last_material_id = info.material_id

    if last_material_id is not None:
        return last_material_id

    # means the new material started
    #  and there's no log records for it
    reading_materials = await database.get_reading_materials()

    if reading_material := safe_list_get(reading_materials, -1, None):
        return reading_material.material_id


async def set_log(*,
                  log: schemas.LogRecord) -> None:
    logger.debug("Setting log: %s", log)

    if log.date in await get_log_records():
        raise ValueError("The date even exists")

    values = {
        'material_id': log.material_id,
        'count': log.count,
        'date': log.date
    }
    stmt = models.ReadingLog\
        .insert().values(values)

    async with database.session() as ses:
        await ses.execute(stmt)

    logger.debug("Log record added")
