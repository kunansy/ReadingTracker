"""Helpers shared by the notes / system / migrations integration tests."""

import asyncio
import base64
import datetime
import json
import uuid
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import sqlalchemy.sql as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import event, inspect
from sqlalchemy.engine import Row

from tracker.common import database, sort_keys
from tracker.common.pagination import Order, Page, PageParams
from tracker.models import models


REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = str(REPO_ROOT / "alembic.ini")
HEAD_REVISION = "0008"

FROZEN_NOW = datetime.datetime(2024, 3, 15, 12, 30, 45)  # noqa: DTZ001
FROZEN_TODAY = FROZEN_NOW.date()


def day(offset: int) -> datetime.date:
    """A date `offset` days after the frozen today (negative: before it)."""
    return FROZEN_TODAY + datetime.timedelta(days=offset)


def at(
    date: datetime.date,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
) -> datetime.datetime:
    return datetime.datetime.combine(date, datetime.time(hour, minute, second))


async def execute(stmt: Any, params: Any = None) -> None:
    async with database.session() as ses:
        await ses.execute(stmt, params)


async def fetch_all(query: str, **params: Any) -> list[Row]:
    async with database.session() as ses:
        return list((await ses.execute(sa.text(query), params)).all())


async def scalar(query: str, **params: Any) -> Any:
    async with database.session() as ses:
        return await ses.scalar(sa.text(query), params)


async def insert_raw_note(
    *,
    material_id: uuid.UUID,
    note_id: uuid.UUID | None = None,
    chapter: str = "1",
    page: int = 1,
    **columns: Any,
) -> uuid.UUID:
    """Insert a note bypassing `notes_db.insert_note`, e.g. to control added_at or tags."""
    note_id = note_id or uuid.uuid4()
    values = {
        "note_id": note_id,
        "material_id": material_id,
        "content": "Raw note.",
        "chapter": chapter,
        "page": page,
        "tags": [],
        "sort_key": sort_keys.note_sort_key(
            material_id=material_id,
            chapter=chapter,
            page=page,
            note_id=note_id,
        ),
        **columns,
    }
    await execute(models.Notes.insert().values(values))
    return note_id


async def insert_repeat(
    *,
    material_id: uuid.UUID,
    repeated_at: datetime.datetime,
) -> uuid.UUID:
    repeat_id = uuid.uuid4()
    await execute(
        models.Repeats.insert().values(
            repeat_id=repeat_id,
            material_id=material_id,
            repeated_at=repeated_at,
        ),
    )
    return repeat_id


async def insert_note_repeat(
    *,
    note_id: uuid.UUID,
    repeated_at: datetime.datetime,
    user_id: int = 1,
) -> uuid.UUID:
    repeat_id = uuid.uuid4()
    await execute(
        models.NoteRepeatsHistory.insert().values(
            repeat_id=repeat_id,
            note_id=note_id,
            user_id=user_id,
            repeated_at=repeated_at,
        ),
    )
    return repeat_id


async def collect_pages[T](
    fetch: Callable[[PageParams], Awaitable[Page[T]]],
    *,
    page_size: int,
    order: Order | None = None,
) -> list[Page[T]]:
    """Walk the listing to its end; a token must come only with a full page."""
    pages: list[Page[T]] = []
    params = PageParams(page_size=page_size, order=order)

    while True:
        page = await fetch(params)
        pages.append(page)
        assert len(page.items) <= page_size
        if page.next_token is None:
            return pages

        assert len(page.items) == page_size
        params = PageParams(next_token=page.next_token, page_size=page_size, order=order)


def page_items[T](pages: list[Page[T]]) -> list[T]:
    return [item for page in pages for item in page.items]


def decode_token(token: str) -> dict[str, dict[str, str]]:
    return json.loads(base64.urlsafe_b64decode(token))


def encode_token(payload: object) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def with_cursor(token: str, cursor: str) -> str:
    payload = decode_token(token)
    payload["continue_from"]["cursor"] = cursor
    return encode_token(payload)


@contextmanager
def captured_statements() -> Iterator[list[tuple[str, Any]]]:
    """Statements the application sends to PostgreSQL, with their parameters."""
    statements: list[tuple[str, Any]] = []

    def capture(conn, cursor, statement, parameters, context, executemany) -> None:  # noqa: ANN001, ARG001
        statements.append((statement, parameters))

    sync_engine = database.engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", capture)
    try:
        yield statements
    finally:
        event.remove(sync_engine, "before_cursor_execute", capture)


async def explain(statement: str, parameters: Any) -> str:
    """Plan of the statement when the planner may only fall back to scanning or sorting.

    On a test-sized table the planner prefers a sequential scan or a bitmap scan plus a sort,
    which says nothing about whether an index can serve the query in order.
    """
    async with database.engine.connect() as conn:
        for setting in ("enable_seqscan", "enable_bitmapscan", "enable_sort"):
            await conn.exec_driver_sql(f"SET LOCAL {setting} = off")
        rows = (await conn.exec_driver_sql(f"EXPLAIN {statement}", parameters)).all()
        await conn.rollback()

    return "\n".join(row[0] for row in rows)


def alembic_config(**kwargs: Any) -> Config:
    return Config(ALEMBIC_INI, **kwargs)


async def alembic_upgrade(revision: str) -> None:
    # env.py calls asyncio.run(), which needs a thread without a running loop
    await asyncio.to_thread(command.upgrade, alembic_config(), revision)
    # pooled connections cache statements prepared against the previous schema
    await database.engine.dispose()


async def alembic_downgrade(revision: str) -> None:
    await asyncio.to_thread(command.downgrade, alembic_config(), revision)
    await database.engine.dispose()


async def current_revision() -> str | None:
    if not await scalar("SELECT to_regclass('alembic_version')"):
        return None
    return await scalar("SELECT version_num FROM alembic_version")


async def drop_everything() -> None:
    async with database.engine.begin() as conn:
        await conn.execute(sa.text("DROP SCHEMA public CASCADE"))
        await conn.execute(sa.text("CREATE SCHEMA public"))
    # pooled connections cache statements prepared against the dropped tables
    await database.engine.dispose()


async def reset_schema_to_head() -> None:
    """Leave the database as the session fixture made it: migrated to head, empty tables."""
    await drop_everything()
    await database.create_db()
    await database.engine.dispose()


async def schema_snapshot() -> dict[str, Any]:
    """Columns, indexes and unique constraints of every table, to compare two schemas."""

    def snapshot(sync_conn) -> dict[str, Any]:  # noqa: ANN001
        inspector = inspect(sync_conn)
        return {
            table: {
                "columns": {
                    column["name"]: (str(column["type"]), column["nullable"])
                    for column in inspector.get_columns(table)
                },
                "indexes": {
                    index["name"]: (tuple(index["column_names"]), index["unique"])
                    for index in inspector.get_indexes(table)
                },
                "unique": {
                    constraint["name"]: tuple(constraint["column_names"])
                    for constraint in inspector.get_unique_constraints(table)
                },
            }
            for table in sorted(inspector.get_table_names())
        }

    async with database.engine.connect() as conn:
        return await conn.run_sync(snapshot)
