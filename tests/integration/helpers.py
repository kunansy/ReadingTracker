"""Clock, query and pagination helpers shared by every integration suite."""

import base64
import datetime
import json
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from typing import Any

import sqlalchemy.sql as sa
from sqlalchemy import event
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Row

from tracker.common import database
from tracker.common.pagination import Order, Page, PageParams


NOW = datetime.datetime(2024, 3, 15, 12, 30, 45, 123456)  # noqa: DTZ001
TODAY = NOW.date()


def day(offset: int) -> datetime.date:
    """A date `offset` days after the frozen `TODAY` (negative: before it)."""
    return TODAY + datetime.timedelta(days=offset)


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


async def fetch_table(table: sa.Table, *order_by: sa.ColumnElement) -> list[dict[str, Any]]:
    async with database.session() as ses:
        rows = (await ses.execute(sa.select(table).order_by(*order_by))).mappings().all()
    return [dict(row) for row in rows]


async def scalar(query: str, **params: Any) -> Any:
    async with database.session() as ses:
        return await ses.scalar(sa.text(query), params)


async def walk_pages[T](
    fetch: Callable[[PageParams], Awaitable[Page[T]]],
    *,
    page_size: int,
    order: Order | None = None,
    max_pages: int = 50,
) -> list[Page[T]]:
    """Walk the listing to its end; a token must come only with a full page."""
    pages: list[Page[T]] = []
    params = PageParams(page_size=page_size, order=order)

    while len(pages) < max_pages:
        page = await fetch(params)
        pages.append(page)
        assert len(page.items) <= page_size
        if page.next_token is None:
            return pages

        assert len(page.items) == page_size
        params = PageParams(next_token=page.next_token, page_size=page_size, order=order)

    raise AssertionError(f"The walk did not end in {max_pages} pages")


def page_items[T](pages: list[Page[T]]) -> list[T]:
    return [item for page in pages for item in page.items]


def decode_token(token: str) -> dict[str, Any]:
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


async def explain(statement: sa.Select | str, parameters: Any = None) -> str:
    """Plan of the statement when the planner may only fall back to scanning or sorting.

    On a test-sized table the planner prefers a sequential scan or a bitmap scan plus a sort,
    which says nothing about whether an index can serve the query in order.
    """
    if isinstance(statement, sa.Select):
        statement = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            ),
        )

    async with database.engine.connect() as conn:
        for setting in ("enable_seqscan", "enable_bitmapscan", "enable_sort"):
            await conn.exec_driver_sql(f"SET LOCAL {setting} = off")
        rows = (await conn.exec_driver_sql(f"EXPLAIN {statement}", parameters)).all()
        await conn.rollback()

    return "\n".join(row[0] for row in rows)
