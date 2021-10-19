import datetime
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from uuid import UUID

import sqlalchemy.sql as sa
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tracker.common import models, settings
from tracker.common.log import logger


class DatabaseError(Exception):
    pass


engine = create_async_engine(settings.DB_URI, encoding='utf-8')


@asynccontextmanager
async def session(**kwargs) -> AsyncGenerator[AsyncSession, None]:
    new_session = AsyncSession(**kwargs, bind=engine, expire_on_commit=False)
    try:
        yield new_session
        await new_session.commit()
    except Exception as e:
        logger.exception("Error with the session")

        await new_session.rollback()
        raise DatabaseError(e)
    finally:
        await new_session.close()


def today() -> datetime.datetime:
    return datetime.datetime.utcnow()


def yesterday() -> datetime.datetime:
    return today() - datetime.timedelta(days=1)


async def get_completion_dates() -> dict[UUID, datetime.date]:
    logger.debug("Getting completion dates")

    stmt = sa.select([models.Materials.c.material_id,
                      models.Statuses.c.completed_at]) \
        .join(models.Statuses,
              models.Statuses.c.material_id == models.Materials.c.material_id) \
        .where(models.Statuses.completed_at != None)

    async with session() as ses:
        return {
            row.material_id: row.completed_at
            async for row in await ses.stream(stmt)
        }


async def get_material_titles() -> dict[UUID, str]:
    logger.debug("Getting material titles")

    stmt = sa.select([models.Materials.c.material_id,
                      models.Materials.c.title])

    async with session() as ses:
        return {
            row.material_id: row.title
            async for row in await ses.stream(stmt)
        }


async def get_reading_materials() -> list[RowMapping]:
    logger.debug("Getting reading materials")

    stmt = sa.select([models.Materials,
                      models.Statuses]) \
        .join(models.Statuses,
              models.Materials.c.material_id == models.Statuses.c.material_id) \
        .where(models.Statuses.c.completed_at == None)

    async with session() as ses:
        return (await ses.execute(stmt)).mappings().all()
