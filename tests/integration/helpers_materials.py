"""Clock and material history helpers shared by the materials / reading log / cards suites."""

import datetime
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest

from tests.integration import factories, helpers
from tests.integration.helpers import day
from tracker.common import database
from tracker.materials import db as materials_db
from tracker.models import enums
from tracker.reading_log import db as logs_db


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
    now: datetime.datetime = helpers.NOW,
) -> Clock:
    clock = Clock(now)
    monkeypatch.setattr(database, "utcnow", clock.utcnow)
    monkeypatch.setattr(database, "utc_today", clock.utc_today)
    return clock


def _ticked(clock: Clock, material: dict[str, Any]) -> dict[str, Any]:
    """Tick the clock first so `added_at` and `sort_key` of the material are distinct."""
    clock.tick()
    return {"title": f"Material at {clock.now.isoformat()}"} | material


async def queued(clock: Clock, **material: Any) -> UUID:
    return await factories.insert_material(**_ticked(clock, material))


async def reading(clock: Clock, *, started: datetime.date, **material: Any) -> UUID:
    return await factories.start_material(started=started, **_ticked(clock, material))


async def completed(
    clock: Clock,
    *,
    started: datetime.date,
    finished: datetime.date,
    **material: Any,
) -> UUID:
    return await factories.complete_material(
        started=started,
        completed=finished,
        **_ticked(clock, material),
    )


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

    day(-10)  book 30
    day(-9)   book 50, article 10
    day(-8)   nothing
    day(-7)   book 22, the book is completed
    day(-6)   article 5
    day(-5) .. today: nothing
    """
    book = await reading(clock, started=day(-10), title="Book", pages=BOOK_PAGES)
    article = await reading(
        clock,
        started=day(-9),
        title="Article",
        pages=ARTICLE_PAGES,
        material_type=enums.MaterialTypesEnum.article,
    )
    book_first = await logs_db.insert_log_record(material_id=book, count=30, date=day(-10))
    book_max = await logs_db.insert_log_record(material_id=book, count=50, date=day(-9))
    article_max = await logs_db.insert_log_record(
        material_id=article, count=10, date=day(-9)
    )
    book_last = await logs_db.insert_log_record(material_id=book, count=22, date=day(-7))
    article_min = await logs_db.insert_log_record(
        material_id=article, count=5, date=day(-6)
    )
    await materials_db.complete_material(material_id=book, completed_at=day(-7))

    return ReadingHistory(
        book=book,
        article=article,
        book_first=book_first,
        book_max=book_max,
        book_last=book_last,
        article_max=article_max,
        article_min=article_min,
    )


__all__ = [
    "ARTICLE_PAGES",
    "BOOK_PAGES",
    "MISSING_ID",
    "Clock",
    "ReadingHistory",
    "completed",
    "freeze_clock",
    "queued",
    "reading",
    "reading_history",
    "repeat",
]
