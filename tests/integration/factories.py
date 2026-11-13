"""Rows for integration tests, written through the public db API.

Each helper returns the id of what it created, so a test reads back exactly its own writes.
"""

import datetime
import uuid
from typing import Any

import sqlalchemy.sql as sa
from sqlalchemy import Table

from tracker.cards import db as cards_db
from tracker.common import database
from tracker.materials import db as materials_db
from tracker.models import enums, models
from tracker.notes import db as notes_db
from tracker.reading_log import db as logs_db


def days_ago(days: int) -> datetime.date:
    return database.utc_today() - datetime.timedelta(days=days)


async def insert_material(
    *,
    title: str | None = None,
    authors: str = "Author",
    pages: int = 100,
    material_type: enums.MaterialTypesEnum = enums.MaterialTypesEnum.book,
    tags: str | None = None,
    link: str | None = None,
) -> uuid.UUID:
    return await materials_db.insert_material(
        title=title or f"Material {uuid.uuid4()}",
        authors=authors,
        pages=pages,
        material_type=material_type,
        tags=tags,
        link=link,
    )


async def start_material(
    *,
    started_days_ago: int = 10,
    **material: Any,
) -> uuid.UUID:
    material_id = await insert_material(**material)
    await materials_db.start_material(
        material_id=material_id,
        started_at=days_ago(started_days_ago),
    )
    return material_id


async def complete_material(
    *,
    started_days_ago: int = 10,
    completed_days_ago: int = 1,
    **material: Any,
) -> uuid.UUID:
    material_id = await start_material(started_days_ago=started_days_ago, **material)
    await materials_db.complete_material(
        material_id=material_id,
        completed_at=days_ago(completed_days_ago),
    )
    return material_id


async def insert_log(
    *,
    material_id: uuid.UUID,
    count: int = 10,
    date: datetime.date | None = None,
) -> uuid.UUID:
    return await logs_db.insert_log_record(
        material_id=material_id,
        count=count,
        date=date or days_ago(1),
    )


async def insert_note(
    *,
    material_id: uuid.UUID,
    content: str = "Note content.",
    title: str | None = None,
    link_id: uuid.UUID | None = None,
    chapter: str = "1",
    page: int = 1,
    tags: list[str] | None = None,
) -> uuid.UUID:
    return await notes_db.insert_note(
        material_id=material_id,
        link_id=link_id,
        title=title,
        content=content,
        chapter=chapter,
        page=page,
        tags=tags or [],
    )


async def insert_card(
    *,
    material_id: uuid.UUID,
    note_id: uuid.UUID,
    question: str = "Question?",
    answer: str | None = "Answer.",
) -> uuid.UUID:
    return await cards_db.add_card(
        material_id=material_id,
        note_id=note_id,
        question=question,
        answer=answer,
    )


async def set_columns(table: Table, row_id: uuid.UUID, **values: Any) -> None:
    """Overwrite columns the public API fills from the clock, e.g. added_at or repeated_at."""
    primary_key = next(iter(table.primary_key.columns))
    stmt = table.update().values(**values).where(primary_key == row_id)

    async with database.session() as ses:
        result = await ses.execute(stmt)

    database.check_updated_one(result, entity=table.name, entity_id=row_id)


async def fetch_row(table: Table, row_id: uuid.UUID) -> dict[str, Any] | None:
    primary_key = next(iter(table.primary_key.columns))
    stmt = sa.select(table).where(primary_key == row_id)

    async with database.session() as ses:
        row = (await ses.execute(stmt)).mappings().one_or_none()

    return dict(row) if row else None


async def count_rows(table: Table) -> int:
    async with database.session() as ses:
        return await ses.scalar(sa.select(sa.func.count()).select_from(table)) or 0


async def refresh_repeat_notes_matview() -> None:
    async with database.session() as ses:
        await ses.execute(sa.text("REFRESH MATERIALIZED VIEW mvw_repeat_notes"))


__all__ = [
    "complete_material",
    "count_rows",
    "days_ago",
    "fetch_row",
    "insert_card",
    "insert_log",
    "insert_material",
    "insert_note",
    "models",
    "refresh_repeat_notes_matview",
    "set_columns",
    "start_material",
]
