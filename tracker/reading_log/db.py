import datetime
from collections import defaultdict
from typing import Any, AsyncGenerator, DefaultDict

import sqlalchemy.sql as sa

from tracker.common import database
from tracker.common.log import logger
from tracker.common.schemas import CustomBaseModel
from tracker.materials import db as materials_db
from tracker.models import models


class LogRecord(CustomBaseModel):
    date: datetime.date
    count: int
    material_id: str
    material_title: str | None = None


def _safe_list_get(lst: list[Any],
                   index: int,
                   default: Any = None) -> Any:
    try:
        return lst[index]
    except IndexError:
        return default


async def get_mean_materials_read_pages() -> dict[str, float]:
    logger.debug("Getting mean reading read pages count of materials")

    stmt = sa.select([models.ReadingLog.c.material_id,
                      sa.func.avg(models.ReadingLog.c.count).label('mean')]) \
        .group_by(models.ReadingLog.c.material_id)

    async with database.session() as ses:
        mean = {
            str(row.material_id): row.mean
            async for row in await ses.stream(stmt)
        }

    logger.debug("Mean material reading got")
    return mean


async def get_log_records() -> list[LogRecord]:
    logger.debug("Getting all log records")

    stmt = sa.select([models.ReadingLog,
                      models.Materials.c.title.label('material_title')])\
        .join(models.Materials,
              models.Materials.c.material_id == models.ReadingLog.c.material_id)

    async with database.session() as ses:
        records = [
            LogRecord(
                date=row.date,
                count=row.count,
                material_id=row.material_id,
                material_title=row.material_title,
            )
            for row in (await ses.execute(stmt)).all()
        ]

    logger.debug("%s log records got", len(records))
    return records


async def get_reading_material_titles() -> dict[str, str]:
    logger.debug("Getting reading material titles")

    stmt = sa.select([models.Materials.c.material_id,
                      models.Materials.c.title])\
        .join(models.Statuses,
              models.Statuses.c.material_id == models.Materials.c.material_id)\
        .where(models.Statuses.c.completed_at == None)

    async with database.session() as ses:
        titles = {
            str(row.material_id): row.title
            async for row in await ses.stream(stmt)
        }

    logger.debug("%s reading materials titles got", len(titles))
    return titles


async def _get_completion_dates() -> dict[str, datetime.datetime]:
    logger.debug("Getting completion dates")

    stmt = sa.select([models.Materials.c.material_id,
                      models.Statuses.c.completed_at]) \
        .join(models.Statuses,
              models.Statuses.c.material_id == models.Materials.c.material_id) \
        .where(models.Statuses.c.completed_at != None)

    async with database.session() as ses:
        dates = {
            str(row.material_id): row.completed_at
            async for row in await ses.stream(stmt)
        }

    logger.debug("%s completion dates got", len(dates))
    return dates


async def data() -> AsyncGenerator[tuple[datetime.date, LogRecord], None]:
    """ Get pairs: (date, info) of all days from start to stop.

    If the day is empty, material_id is supposed
    as the material_id of the last not empty day.
    """
    logger.debug("Getting logging data")

    if not (log_records := await get_log_records()):
        return

    log_records_dict: DefaultDict[datetime.date, list[LogRecord]] = defaultdict(list)
    for log_record in log_records:
        log_records_dict[log_record.date] += [log_record]

    # stack for materials
    materials: list[str] = []
    try:
        completion_dates = await _get_completion_dates()
    except Exception as e:
        logger.exception(e)
        completion_dates = {}

    step = datetime.timedelta(days=1)
    iter_over_dates = min(log_records_dict.keys())

    while iter_over_dates <= database.utcnow().date():
        last_material_id = _safe_list_get(materials, -1, None)

        if ((completion_date := completion_dates.get(last_material_id))
                and completion_date.date() < iter_over_dates):
            materials.pop()
            last_material_id = _safe_list_get(materials, -1, None)

        if not (log_records_ := log_records_dict.get(iter_over_dates)):
            log_record = LogRecord(material_id=last_material_id, count=0, date=iter_over_dates)

            yield iter_over_dates, log_record
            iter_over_dates += step
        else:
            for log_record in log_records_:
                material_id = log_record.material_id

                if not (materials and material_id in materials):
                    # new material started, the last one completed
                    materials += [material_id]
                elif material_id != last_material_id:
                    # in this case several materials
                    # are being reading one by one
                    materials.remove(material_id)
                    materials += [material_id]

                yield iter_over_dates, log_record
            iter_over_dates += step


async def is_log_empty() -> bool:
    logger.debug("Checking the log is empty")
    stmt = sa.select(sa.func.count(1) == 0)\
        .select_from(models.ReadingLog)

    async with database.session() as ses:
        is_empty = await ses.scalar(stmt)

    logger.debug("Log empty: %s", is_empty)
    return is_empty


async def get_material_reading_now() -> str | None:
    logger.debug("Getting material reading now")

    if await is_log_empty():
        logger.warning("Reading log is empty, no materials reading")
        return None

    last_material_id = None
    async for _, info in data():
        last_material_id = info.material_id

    if last_material_id is not None:
        logger.debug("Now %s is reading", last_material_id)
        return last_material_id

    logger.debug("Reading material not found")
    # means the new material started
    #  and there's no log records for it

    material_id = await materials_db.get_last_material_started()
    logger.debug("So, assume the last inserted material is reading: %s", material_id)

    return material_id


async def insert_log_record(*,
                            material_id: str,
                            count: int,
                            date: datetime.date) -> None:
    logger.debug("Inserting log material_id=%s, count=%s, date=%s",
                 material_id, count, date)

    values = {
        'material_id': material_id,
        'count': count,
        'date': date
    }
    stmt = models.ReadingLog \
        .insert().values(values)

    async with database.session() as ses:
        await ses.execute(stmt)

    logger.debug("Log record inserted")
