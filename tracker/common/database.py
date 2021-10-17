import datetime
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import sqlalchemy.sql as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tracker.common import models, settings
from tracker.common.log import logger


class DatabaseError(Exception):
    pass


engine = create_async_engine(settings.DB_URI, encoding='utf-8')
engine.sync_engine.run(models.metadata.create_all())


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


async def get_completion_dates() -> dict[int, datetime.date]:
    logger.debug("Getting completion dates")

    stmt = sa.select([models.Material.c.material_id,
                      models.Status.c.end]) \
        .join(models.Status,
              models.Status.c.material_id == models.Material.c.material_id) \
        .where(models.Status.end != None)

    async with session() as ses:
        return {
            row.material_id: row.end
            async for row in await ses.stream(stmt)
        }


async def get_material_titles() -> dict[int, str]:
    logger.debug("Getting material titles")

    stmt = sa.select([models.Material.c.material_id,
                      models.Material.c.title])

    async with session() as ses:
        return {
            row.material_id: row.title
            async for row in await ses.stream(stmt)
        }
