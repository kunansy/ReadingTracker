import datetime
from typing import Any, AsyncGenerator, NamedTuple, Optional

import sqlalchemy.sql as sa
from sqlalchemy.engine import RowMapping

from tracker.common import database, models
from tracker.common.log import logger
from tracker.reading_log import schemas


class LogRecord(NamedTuple):
    count: int # type: ignore
    material_id: int
    material_title: Optional[str] = None


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
                      models.Materials.c.title.lable('material_title')])\
        .join(models.Materials,
              models.Materials.c.material_id == models.ReadingLog.c.material_id)

    async with database.session() as ses:
        return {
            row.date: row
            async for row in await ses.stream(stmt)
        }


async def get_material_titles() -> dict[int, str]:
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
    materials: list[int] = []
    try:
        completion_dates = await database.get_completion_dates()
    except Exception as e:
        logger.exception(e)
        completion_dates = {}

    step = datetime.timedelta(days=1)
    iter_over_dates = min(log_records.keys())

    while iter_over_dates <= database.today():
        last_material_id = safe_list_get(materials, -1, 0)

        if ((completion_date := completion_dates.get(last_material_id))
                and completion_date < iter_over_dates):
            materials.pop()
            last_material_id = safe_list_get(materials, -1, 0)

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


async def get_material_reading_now() -> Optional[int]:
    if not await get_log_records():
        logger.warning("Reading log is empty, no materials reading")
        return # type: ignore

    last_material_id = 0
    async for _, info in data():
        last_material_id = info.material_id

    if last_material_id != 0:
        return last_material_id

    # means the new material started
    #  and there's no log records for it
    try:
        reading_materials = database.get_reading_materials()
    except Exception:
        logger.exception("Error getting reading materials")
        return 0

    if (reading_material := safe_list_get(reading_materials, -1, 0)) == 0:
        return 0

    return reading_material.material.material_id


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
