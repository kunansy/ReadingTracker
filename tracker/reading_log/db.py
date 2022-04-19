import datetime
from typing import Any, AsyncGenerator, NamedTuple
from uuid import UUID

import sqlalchemy.sql as sa
from sqlalchemy.engine import RowMapping

from tracker.common import database, models
from tracker.common.log import logger


class LogRecord(NamedTuple):
    count: int # type: ignore
    material_id: UUID
    material_title: str | None = None


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


async def get_completion_dates() -> dict[UUID, datetime.date]:
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
    logger.debug("Getting data from log")

    if not (log_records := await get_log_records()):
        return

    # stack for materials
    materials: list[UUID] = []
    try:
        completion_dates = await get_completion_dates()
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


async def get_material_reading_now() -> UUID | None: # type: ignore
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
