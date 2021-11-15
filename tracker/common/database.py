import datetime
from contextlib import asynccontextmanager
from typing import AsyncGenerator, NamedTuple, Optional
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


class MaterialStatistics(NamedTuple):
    material: RowMapping
    started_at: datetime.date
    duration: int
    lost_time: int
    total: int
    min_record: Optional[MinMax]
    max_record: Optional[MinMax]
    average: int
    remaining_pages: Optional[int] = None
    remaining_days: Optional[int] = None
    completed_at: Optional[datetime.date] = None
    # date when the material would be completed
    # according to average read pages count
    would_be_completed: Optional[datetime.date] = None


class LogStatistics(NamedTuple):
    material_id: UUID
    # total spent time including empty days
    total: int
    lost_time: int
    # days the material was being reading
    duration: int
    average: int
    min_record: Optional[MinMax]
    max_record: Optional[MinMax]


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
        .where(models.Statuses.c.completed_at != None)

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


async def get_material_status(*, # type: ignore
                              material_id: UUID) -> Optional[RowMapping]:
    logger.debug("Getting status for material_id=%s",
                 material_id)

    stmt = sa.select(models.Statuses) \
        .where(models.Statuses.c.material_id == str(material_id))

    async with session() as ses:
        if status := (await ses.execute(stmt)).one_or_none():
            return status
