import datetime
from contextlib import asynccontextmanager
from typing import AsyncGenerator, NamedTuple
from uuid import UUID

import sqlalchemy.sql as sa
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tracker.common import models, settings
from tracker.common.log import logger


class DatabaseError(Exception):
    pass


class MinMax(NamedTuple):
    log_id: UUID
    material_id: UUID
    material_title: str
    count: int # type: ignore
    date: datetime.date


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


async def get_reading_materials() -> list[RowMapping]:
    logger.debug("Getting reading materials")

    stmt = sa.select([models.Materials,
                      models.Statuses]) \
        .join(models.Statuses,
              models.Materials.c.material_id == models.Statuses.c.material_id) \
        .where(models.Statuses.c.completed_at == None)\
        .order_by(models.Statuses.c.started_at)

    async with session() as ses:
        return (await ses.execute(stmt)).mappings().all()
