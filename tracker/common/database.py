import datetime
import functools
from contextlib import asynccontextmanager
from typing import AsyncGenerator, NamedTuple, Any
from uuid import UUID

import sqlalchemy.sql as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tracker.common import settings
from tracker.common.log import logger


class DatabaseException(Exception):
    pass


class MinMax(NamedTuple):
    log_id: UUID
    material_id: UUID
    material_title: str
    count: int # type: ignore
    date: datetime.date


engine = create_async_engine(
    settings.DB_URI,
    encoding='utf-8',
    isolation_level=settings.DB_ISOLATION_LEVEL,
    connect_args={'timeout': settings.DB_TIMEOUT}
)

utcnow = datetime.datetime.utcnow


class TTLCache:
    # TTL is 20s
    TTL = 20

    def __init__(self, result: list[dict[str, Any]]):
        self.added_at = utcnow()
        self.result = result

    def is_alive(self) -> bool:
        return (utcnow() - self.added_at).seconds <= self.TTL


def cache(func):
    storage: dict[int, TTLCache] = {}
    name = func.__name__

    @functools.wraps(func)
    async def wrapped(*args, **kwargs):
        nonlocal storage

        hashable_kwargs = {
            k: tuple(v) if isinstance(v, (list, set, dict)) else v
            for k, v in kwargs.items()
        }
        arg = hash((*args, *hashable_kwargs.items()))
        if not (ttl := storage.get(arg)):
            logger.log(5, "%s: got from func", name)

            result = await func(*args, **kwargs)
            storage[arg] = TTLCache(result)
        elif not ttl.is_alive():
            logger.log(5, "%s: cache expired, get the new one", name)

            result = await func(*args, **kwargs)
            storage[arg] = TTLCache(result)
        else:
            logger.log(5, "%s: got from cache", name)

        return storage[arg].result
    return wrapped


@asynccontextmanager
async def session(**kwargs) -> AsyncGenerator[AsyncSession, None]:
    new_session = AsyncSession(**kwargs, bind=engine)
    try:
        yield new_session
        await new_session.commit()
    except Exception as e:
        logger.exception("Error with the session")

        await new_session.rollback()
        raise DatabaseException(e)
    finally:
        await new_session.close()


@asynccontextmanager
async def transaction(**kwargs) -> AsyncGenerator[AsyncSession, None]:
    async with session(**kwargs) as ses:
        async with ses.begin():
            yield ses


async def is_alive() -> bool:
    logger.debug("Checking if the database is alive")

    stmt = sa.select(sa.text("SELECT 1 + 1 = 2"))
    async with session() as ses:
        return await ses.scalar(stmt)
