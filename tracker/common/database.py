import asyncio
import datetime
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, Final, cast
from uuid import UUID

import orjson
import sqlalchemy.sql as sa
from sqlalchemy import inspect
from sqlalchemy.engine import CursorResult, Result
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.ddl import DropTable

from tracker.common import settings
from tracker.common.logger import logger
from tracker.common.schemas import CustomBaseModel
from tracker.models import models


PG_UNIQUE_VIOLATION: Final[str] = "23505"
ALEMBIC_CONFIG: Final[str] = "alembic.ini"
BASELINE_REVISION: Final[str] = "0001"


class DatabaseException(Exception):
    pass


class AlreadyExistsException(DatabaseException):
    pass


class NotFoundException(DatabaseException):
    pass


class ConflictException(DatabaseException):
    pass


INVALID_NEXT_TOKEN_MSG: Final[str] = "Invalid nextToken"  # noqa: S105


class InvalidNextTokenException(DatabaseException):
    pass


class MinMax(CustomBaseModel):
    log_id: UUID | str = ""
    material_id: UUID | str = ""
    material_title: str = ""
    count: int
    date: datetime.date


def _json_serializer(value: Any) -> str:
    return orjson.dumps(value).decode("utf8")


engine = create_async_engine(
    settings.DB_URI,
    isolation_level=settings.DB_ISOLATION_LEVEL,
    connect_args={
        "timeout": settings.DB_TIMEOUT,
        "statement_cache_size": 50,
        "max_cached_statement_lifetime": 0,
    },
    json_deserializer=orjson.loads,
    json_serializer=_json_serializer,
)


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def utc_today() -> datetime.date:
    return utcnow().date()


def check_inserted_one(result: Result[Any], *, entity: str) -> None:
    rowcount = cast("CursorResult[Any]", result).rowcount
    if rowcount != 1:
        msg = f"{entity} insert affected {rowcount} rows, expected 1"
        logger.error(msg)
        raise DatabaseException(msg)


def affected_rows(result: Result[Any]) -> int:
    return cast("CursorResult[Any]", result).rowcount


def check_updated_one(result: Result[Any], *, entity: str, entity_id: object) -> None:
    if affected_rows(result) != 1:
        msg = f"{entity} id={entity_id!r} not found"
        logger.info(msg)
        raise NotFoundException(msg)


def check_state_changed(result: Result[Any], *, msg: str) -> None:
    if affected_rows(result) != 1:
        logger.info(msg)
        raise ConflictException(msg)


@asynccontextmanager
async def session(**kwargs) -> AsyncGenerator[AsyncSession]:
    new_session = AsyncSession(**kwargs, bind=engine)
    try:
        yield new_session
        await new_session.commit()
    except IntegrityError as e:
        if getattr(e.orig, "pgcode", None) == PG_UNIQUE_VIOLATION:
            raise AlreadyExistsException(getattr(e.orig, "args", "")) from None

        await new_session.rollback()
        raise DatabaseException(e) from e
    except Exception as e:
        logger.exception("Error with the session")

        await new_session.rollback()
        raise DatabaseException(e) from e
    finally:
        await new_session.close()


@asynccontextmanager
async def transaction(**kwargs) -> AsyncGenerator[AsyncSession]:
    async with session(**kwargs) as ses, ses.begin():
        yield ses


async def readiness() -> bool:
    logger.log(5, "Checking the database is alive")

    stmt = sa.text("SELECT 1 + 1 = 2")
    try:
        async with session() as ses:
            return await ses.scalar(stmt)
    except Exception as e:
        logger.warning("Fail checking PostgreSQL readiness: %r", e)
        return False


@compiles(DropTable, "postgresql")
def _compile_drop_table(element, compiler, **kwargs) -> str:  # noqa: ANN001, ARG001
    return compiler.visit_drop_table(element) + " CASCADE"


async def _is_unversioned_db() -> bool:
    # A separate engine: the caller runs its own event loop, and the
    # gunicorn master must not hand pooled connections to forked workers.
    migration_engine = create_async_engine(settings.DB_URI)
    try:
        async with migration_engine.connect() as conn:
            tables = await conn.run_sync(
                lambda sync_conn: set(inspect(sync_conn).get_table_names()),
            )
    finally:
        await migration_engine.dispose()

    return "alembic_version" not in tables and models.Materials.name in tables


def migrate_db() -> None:
    """Upgrade the schema to head; a database created before Alembic is stamped first.

    Must be called outside a running event loop, alembic env.py starts its own.
    """
    from alembic import command
    from alembic.config import Config

    config = Config(ALEMBIC_CONFIG)
    if asyncio.run(_is_unversioned_db()):
        logger.info("Database has no alembic version, stamping %s", BASELINE_REVISION)
        command.stamp(config, BASELINE_REVISION)

    command.upgrade(config, "head")
    logger.info("Database migrated to head")


async def create_db() -> None:
    await asyncio.to_thread(migrate_db)
