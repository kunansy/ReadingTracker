"""Clock, row and pagination helpers shared by the materials / reading log / cards suites."""

import base64
import datetime
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy.sql as sa
from sqlalchemy.dialects import postgresql

from tracker.common import database
from tracker.common.pagination import Order, Page, PageParams
from tracker.materials import db as materials_db
from tracker.models import enums, models
from tracker.reading_log import db as logs_db


NOW = datetime.datetime(2024, 3, 15, 12, 30, 45, 123456)
TODAY = NOW.date()
MISSING_ID = UUID("00000000-0000-7000-8000-000000000000")


class Clock:
    """A settable replacement for `database.utcnow` / `database.utc_today`."""

    def __init__(self, now: datetime.datetime) -> None:
        self.now = now

    def utcnow(self) -> datetime.datetime:
        return self.now

    def utc_today(self) -> datetime.date:
        return self.now.date()

    def tick(self, seconds: int = 1) -> datetime.datetime:
        self.now += datetime.timedelta(seconds=seconds)
        return self.now


def freeze_clock(
    monkeypatch: pytest.MonkeyPatch,
    now: datetime.datetime = NOW,
) -> Clock:
    clock = Clock(now)
    monkeypatch.setattr(database, "utcnow", clock.utcnow)
    monkeypatch.setattr(database, "utc_today", clock.utc_today)
    return clock


def day(days_ago: int) -> datetime.date:
    """A date relative to the frozen `TODAY`."""
    return TODAY - datetime.timedelta(days=days_ago)


def midnight(date: datetime.date) -> datetime.datetime:
    return datetime.datetime.combine(date, datetime.time())


async def queued(clock: Clock, **material: Any) -> UUID:
    """Insert a queued material; the clock ticks first so `added_at` and `sort_key` are distinct."""
    clock.tick()
    values = {
        "title": f"Material at {clock.now.isoformat()}",
        "authors": "Author",
        "pages": 100,
        "material_type": enums.MaterialTypesEnum.book,
        "tags": None,
        "link": None,
    } | material
    return await materials_db.insert_material(**values)


async def reading(clock: Clock, *, started: datetime.date, **material: Any) -> UUID:
    material_id = await queued(clock, **material)
    await materials_db.start_material(material_id=material_id, started_at=started)
    return material_id


async def completed(
    clock: Clock,
    *,
    started: datetime.date,
    finished: datetime.date,
    **material: Any,
) -> UUID:
    material_id = await reading(clock, started=started, **material)
    await materials_db.complete_material(material_id=material_id, completed_at=finished)
    return material_id


async def repeat(clock: Clock, material_id: UUID, *, at: datetime.datetime) -> None:
    current = clock.now
    clock.now = at
    try:
        await materials_db.repeat_material(material_id=material_id)
    finally:
        clock.now = current


@dataclass(frozen=True)
class ReadingHistory:
    book: UUID
    article: UUID
    book_first: UUID
    book_max: UUID
    book_last: UUID
    article_max: UUID
    article_min: UUID


BOOK_PAGES = 102
ARTICLE_PAGES = 40


async def reading_history(clock: Clock) -> ReadingHistory:
    """A completed book and an article still being read, relative to the frozen `TODAY`.

    day(10)  book 30
    day(9)   book 50, article 10
    day(8)   nothing
    day(7)   book 22, the book is completed
    day(6)   article 5
    day(5) .. today: nothing
    """
    book = await reading(clock, started=day(10), title="Book", pages=BOOK_PAGES)
    article = await reading(
        clock,
        started=day(9),
        title="Article",
        pages=ARTICLE_PAGES,
        material_type=enums.MaterialTypesEnum.article,
    )
    book_first = await logs_db.insert_log_record(material_id=book, count=30, date=day(10))
    book_max = await logs_db.insert_log_record(material_id=book, count=50, date=day(9))
    article_max = await logs_db.insert_log_record(
        material_id=article, count=10, date=day(9)
    )
    book_last = await logs_db.insert_log_record(material_id=book, count=22, date=day(7))
    article_min = await logs_db.insert_log_record(
        material_id=article, count=5, date=day(6)
    )
    await materials_db.complete_material(material_id=book, completed_at=day(7))

    return ReadingHistory(
        book=book,
        article=article,
        book_first=book_first,
        book_max=book_max,
        book_last=book_last,
        article_max=article_max,
        article_min=article_min,
    )


async def fetch_all(table: sa.Table, *order_by: sa.ColumnElement) -> list[dict[str, Any]]:
    async with database.session() as ses:
        rows = (await ses.execute(sa.select(table).order_by(*order_by))).mappings().all()
    return [dict(row) for row in rows]


async def walk[T](
    fetch: Callable[[PageParams], Awaitable[Page[T]]],
    *,
    page_size: int,
    order: Order | None = None,
    max_pages: int = 50,
) -> list[Page[T]]:
    """Follow next tokens until the listing ends; every page is returned for inspection."""
    pages: list[Page[T]] = []
    params = PageParams(page_size=page_size, order=order)
    while len(pages) < max_pages:
        page = await fetch(params)
        pages.append(page)
        if page.next_token is None:
            return pages
        params = PageParams(next_token=page.next_token, page_size=page_size, order=order)
    raise AssertionError(f"The walk did not end in {max_pages} pages")


def decode_token(token: str) -> dict[str, Any]:
    return json.loads(base64.urlsafe_b64decode(token))


def encode_token(payload: object) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def with_cursor(token: str, cursor: str) -> str:
    payload = decode_token(token)
    payload["continue_from"]["cursor"] = cursor
    return encode_token(payload)


async def explain(stmt: sa.Select) -> str:
    """The plan of `stmt` with sequential and bitmap scans disabled: a usable index must show up."""
    sql = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        ),
    )
    async with database.session() as ses:
        await ses.execute(sa.text("SET LOCAL enable_seqscan = off"))
        await ses.execute(sa.text("SET LOCAL enable_bitmapscan = off"))
        conn = await ses.connection()
        rows = (await conn.exec_driver_sql(f"EXPLAIN {sql}")).all()
    return "\n".join(row[0] for row in rows)


__all__ = [
    "ARTICLE_PAGES",
    "BOOK_PAGES",
    "MISSING_ID",
    "NOW",
    "TODAY",
    "Clock",
    "ReadingHistory",
    "completed",
    "day",
    "decode_token",
    "encode_token",
    "explain",
    "fetch_all",
    "freeze_clock",
    "midnight",
    "models",
    "queued",
    "reading",
    "reading_history",
    "repeat",
    "walk",
    "with_cursor",
]
