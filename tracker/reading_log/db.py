from datetime import datetime
from typing import Optional

import sqlalchemy.sql as sa
from sqlalchemy.engine import RowMapping

from tracker.common import database, models
from tracker.common.log import logger
from tracker.reading_log import schemas


async def get_log_records() -> dict[datetime.date, RowMapping]:
    logger.debug("Getting all log records")

    stmt = sa.select([models.ReadingLog,
                      models.Material.c.title.lable('material_title')])\
        .join(models.Material,
              models.Material.c.material_id == models.ReadingLog.c.material_id)

    async with database.session() as ses:
        return {
            row.date.date(): row
            async for row in await ses.stream(stmt)
        }


async def get_material_reading_now() -> Optional[RowMapping]:
    pass


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
