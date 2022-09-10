import datetime
from collections import defaultdict
from typing import Any, AsyncGenerator, NamedTuple, DefaultDict
from uuid import UUID

import sqlalchemy.sql as sa

from tracker.common import database
from tracker.models import models
from tracker.common.log import logger
from tracker.materials import db as materials_db


class LogRecord(NamedTuple):
    date: datetime.date
    count: int # type: ignore
    material_id: UUID
    material_title: str | None = None


def _safe_list_get(list_: list[Any],
                   index: int,
                   default: Any = None) -> Any:
    try:
        return list_[index]
    except IndexError:
        return default


async def get_average_materials_read_pages() -> dict[UUID, float]:
    logger.debug("Getting average reading read pages count of materials")

    stmt = sa.select([models.ReadingLog.c.material_id,
                      sa.func.avg(models.ReadingLog.c.count)]) \
        .group_by(models.ReadingLog.c.material_id)

    async with database.session() as ses:
        return {
            row.material_id: row.avg
            async for row in await ses.stream(stmt)
        }


async def get_log_records() -> list[LogRecord]:
    logger.debug("Getting all log records")

    stmt = sa.select([models.ReadingLog,
                      models.Materials.c.title.label('material_title')])\
        .join(models.Materials,
              models.Materials.c.material_id == models.ReadingLog.c.material_id)

    async with database.session() as ses:
        return [
            LogRecord(
                date=row.date,
                count=row.count,
                material_id=row.material_id,
                material_title=row.material_title,
            )
            for row in (await ses.execute(stmt)).all()
        ]


async def get_reading_material_titles() -> dict[UUID, str]:
    logger.debug("Getting material titles")

    stmt = sa.select([models.Materials.c.material_id,
                      models.Materials.c.title])\
        .join(models.Statuses,
              models.Statuses.c.material_id == models.Materials.c.material_id)\
        .where(models.Statuses.c.completed_at == None)

    async with database.session() as ses:
        return {
            row.material_id: row.title
            async for row in await ses.stream(stmt)
        }


async def _get_completion_dates() -> dict[UUID, datetime.date]:
    logger.debug("Getting completion dates")

    stmt = sa.select([models.Materials.c.material_id,
                      models.Statuses.c.completed_at]) \
        .join(models.Statuses,
              models.Statuses.c.material_id == models.Materials.c.material_id) \
        .where(models.Statuses.c.completed_at != None)

    async with database.session() as ses:
        return {
            row.material_id: row.completed_at
            async for row in await ses.stream(stmt)
        }


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
    materials: list[UUID] = []
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
                and completion_date < iter_over_dates):
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


async def get_material_reading_now() -> UUID | None:
    if not await get_log_records():
        logger.warning("Reading log is empty, no materials reading")
        return None

    last_material_id = None
    async for _, info in data():
        last_material_id = info.material_id

    if last_material_id is not None:
        return last_material_id

    # means the new material started
    #  and there's no log records for it
    return await materials_db.get_last_material_started()


async def set_log(*,
                  material_id: UUID,
                  count: int,
                  date: datetime.date) -> None:
    logger.debug("Setting log for material_id=%s, count=%s, date=%s: ",
                 material_id, count, date)

    values = {
        'material_id': str(material_id),
        'count': count,
        'date': date
    }
    stmt = models.ReadingLog \
        .insert().values(values)

    async with database.session() as ses:
        await ses.execute(stmt)

    logger.debug("Log record added")
