import datetime
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import orjson
import sqlalchemy.sql as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.ddl import DropTable

from tracker.common import settings
from tracker.common.logger import logger
from tracker.common.schemas import CustomBaseModel
from tracker.models import enums, models


class DatabaseException(Exception):
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


@asynccontextmanager
async def session(**kwargs) -> AsyncGenerator[AsyncSession]:
    new_session = AsyncSession(**kwargs, bind=engine)
    try:
        yield new_session
        await new_session.commit()
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


async def create_repeat_notes_matview(conn: AsyncSession | AsyncConnection) -> None:
    # repeat notes that were repeated the longest ago
    query = """
    CREATE MATERIALIZED VIEW IF NOT EXISTS mvw_repeat_notes AS
        WITH sample_notes AS (
            SELECT
                n.note_id,
                n.material_id,
                n.page,
                n.chapter,
                n.title,
                n.content,
                n.added_at,
                n.tags,
                COUNT(1) OVER () AS total_notes_count
            FROM notes n
            WHERE NOT n.is_deleted
        ),
        last_material_repeat AS (
            SELECT
                r.material_id,
                max(r.repeated_at) AS repeated_at,
                COUNT(1) AS repeats_count
            FROM repeats r
            GROUP BY r.material_id
        ),
        last_note_repeat_date AS (
            SELECT
                max(rh.repeated_at::date) as date,
                n.note_id
            FROM
                note_repeats_history rh
            FULL OUTER JOIN
                notes n ON n.note_id = rh.note_id
            WHERE
                n is null or not n.is_deleted
            GROUP BY n.note_id
        ), oldest_notes AS (
            SELECT
                DATE_TRUNC('month', lrd.date) as date,
                ARRAY_AGG(lrd.note_id) AS notes
            FROM
                last_note_repeat_date lrd
            GROUP BY
                date
            ORDER BY
                date NULLS FIRST, COUNT(1)
            LIMIT 1
        )
        SELECT
            n.note_id,
            m.material_id,
            m.title AS material_title,
            m.authors AS material_authors,
            m.material_type AS material_type,
            n.content,
            n.added_at,
            n.chapter,
            n.page,
            n.tags,
            m.pages AS material_pages,
            n.total_notes_count AS total_notes_count,
            0 AS min_repeat_freq,
            CASE
                -- in this case the note have no material
                WHEN m IS NULL THEN 'completed'
                WHEN s IS NULL THEN 'queue'
                WHEN s.completed_at IS NULL THEN 'reading'
                ELSE 'completed'
            END AS material_status,
            r.repeated_at,
            r.repeats_count
        FROM
            sample_notes n
        JOIN oldest_notes ON n.note_id = ANY(oldest_notes.notes)
        LEFT JOIN materials m ON n.material_id = m.material_id
        LEFT JOIN statuses s ON s.material_id = m.material_id
        LEFT JOIN last_material_repeat r ON r.material_id = s.material_id
    WITH NO DATA;
    """

    await conn.execute(sa.text(query))


async def _create_zero_material(
    conn: AsyncConnection,
    *,
    started_at: datetime.date | None = None,
    completed_at: datetime.date | None = None,
) -> None:
    material_id = str(UUID(int=0))
    material = {
        "material_id": material_id,
        "title": "Without material",
        "authors": "",
        "pages": 0,
        "material_type": enums.MaterialTypesEnum.book,
        "is_outlined": True,
    }
    insert_material_stmt = models.Materials.insert().values(material)

    status = {
        "material_id": material_id,
        "started_at": started_at or utcnow().date(),
        "completed_at": completed_at or utcnow().date(),
    }
    insert_status_stmt = models.Statuses.insert().values(status)

    reading_log = {
        "material_id": material_id,
        "count": 0,
        "date": started_at or completed_at or utcnow().date(),
    }
    insert_reading_log_stmt = models.ReadingLog.insert().values(reading_log)

    await conn.execute(insert_material_stmt)
    await conn.execute(insert_status_stmt)
    await conn.execute(insert_reading_log_stmt)


async def recreate_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(models.metadata.drop_all)
        await conn.run_sync(models.metadata.create_all)
        await create_repeat_notes_matview(conn)
        await _create_zero_material(conn)


async def create_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(models.metadata.create_all)
        await create_repeat_notes_matview(conn)
