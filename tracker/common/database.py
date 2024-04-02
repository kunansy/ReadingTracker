import datetime
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

import sqlalchemy.sql as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.ddl import DropTable

from tracker.common import settings
from tracker.common.logger import logger
from tracker.common.schemas import CustomBaseModel
from tracker.models import models


class DatabaseException(Exception):
    pass


class MinMax(CustomBaseModel):
    log_id: UUID | str = ""
    material_id: UUID | str = ""
    material_title: str = ""
    count: int
    date: datetime.date


engine = create_async_engine(
    settings.DB_URI,
    isolation_level=settings.DB_ISOLATION_LEVEL,
    connect_args={
        "timeout": settings.DB_TIMEOUT,
        "statement_cache_size": 50,
        "max_cached_statement_lifetime": 0,
    },
)


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


@asynccontextmanager
async def session(**kwargs) -> AsyncGenerator[AsyncSession, None]:
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
async def transaction(**kwargs) -> AsyncGenerator[AsyncSession, None]:
    async with session(**kwargs) as ses, ses.begin():
        yield ses


async def readiness() -> bool:
    logger.log(5, "Checking the database is alive")

    stmt = sa.text("SELECT 1 + 1 = 2")
    async with session() as ses:
        return await ses.scalar(stmt)


@compiles(DropTable, "postgresql")
def _compile_drop_table(element, compiler, **kwargs) -> str:  # noqa: ANN001, ARG001
    return compiler.visit_drop_table(element) + " CASCADE"


async def create_repeat_notes_matview(conn: AsyncSession | AsyncConnection) -> None:
    query = """
    CREATE MATERIALIZED VIEW IF NOT EXISTS mvw_repeat_notes AS
        WITH repeated_notes_freq AS (
            SELECT note_id, COUNT(1)
            FROM note_repeats_history
            GROUP BY note_id
        ),
        all_notes_freq AS (
            SELECT
                n.material_id,
                n.note_id AS note_id,
                COALESCE(s.count, 0) AS count,
                COUNT(1) OVER () AS total
            FROM notes n
            LEFT JOIN repeated_notes_freq s USING(note_id)
            WHERE NOT n.is_deleted
        ),
        min_freq AS (
            SELECT count
            FROM all_notes_freq
            ORDER BY count
            LIMIT 1
        ),
        sample_notes AS (
            SELECT
                n.note_id,
                n.material_id,
                n.page,
                n.chapter,
                n.title,
                n.content,
                n.added_at,
                f.total AS total_notes_count,
                -- m.total AS total_freq_count,
                m.count AS min_repeat_freq
            FROM all_notes_freq f
            JOIN min_freq m ON f.count = m.count
            JOIN notes n ON f.note_id = n.note_id
        ),
        last_repeat AS (
            SELECT
                m.material_id,
                r.repeated_at,
                COUNT(1) OVER (PARTITION BY r.material_id) AS repeats_count
            FROM sample_notes n
            JOIN materials m USING(material_id)
            JOIN repeats r USING(material_id)
            ORDER BY r.repeated_at DESC
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
            m.pages AS material_pages,
            n.total_notes_count AS total_notes_count,
            n.min_repeat_freq AS min_repeat_freq,
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
        LEFT JOIN materials m ON n.material_id = m.material_id
        LEFT JOIN statuses s ON s.material_id = m.material_id
        LEFT JOIN last_repeat r ON r.material_id = s.material_id
    WITH NO DATA;
    """

    await conn.execute(sa.text(query))


async def recreate_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(models.metadata.drop_all)
        await conn.run_sync(models.metadata.create_all)
        await create_repeat_notes_matview(conn)


async def create_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(models.metadata.create_all)
        await create_repeat_notes_matview(conn)
