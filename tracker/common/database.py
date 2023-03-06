import datetime
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import sqlalchemy.sql as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.ddl import DropTable

from tracker.common import settings
from tracker.common.logger import logger
from tracker.common.schemas import CustomBaseModel
from tracker.models import models


class DatabaseException(Exception):
    pass


class MinMax(CustomBaseModel):
    log_id: str
    material_id: str
    material_title: str
    count: int
    date: datetime.date


engine = create_async_engine(
    settings.DB_URI,
    isolation_level=settings.DB_ISOLATION_LEVEL,
    connect_args={'timeout': settings.DB_TIMEOUT}
)

utcnow = datetime.datetime.utcnow


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


async def readiness() -> bool:
    logger.log(5, "Checking the database is alive")

    stmt = sa.text("SELECT 1 + 1 = 2")
    async with session() as ses:
        return await ses.scalar(stmt)


@compiles(DropTable, "postgresql")
def _compile_drop_table(element, compiler, **kwargs):
    return compiler.visit_drop_table(element) + " CASCADE"


async def recreate_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(models.metadata.drop_all)
        await conn.run_sync(models.metadata.create_all)


async def create_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(models.metadata.create_all)
