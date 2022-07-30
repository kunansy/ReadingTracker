import asyncio
import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import NamedTuple, Sequence, Generator

import sqlalchemy.sql as sa

from tracker.common.log import logger
from tracker.models import models
from tracker.common import database, settings


class TrendException(database.DatabaseError):
    pass


class DayStatistics(NamedTuple):
    date: datetime.date
    amount: int

    def __str__(self) -> str:
        return f"{self.date.strftime(settings.DATE_FORMAT)}: {self.amount}"


@dataclass
class WeekStatistics:
    data: list[DayStatistics]

    def __init__(self, days: Sequence[tuple[datetime.date, int]]) -> None:
        if len(days) != 7:
            raise TrendException(
                f"A week should contains exactly 7 days, but {len(days)} found")

        self.data = [
            DayStatistics(date=date, amount=amount)
            for date, amount in days
        ]

    @property
    def start(self) -> datetime.date:
        if not self.data:
            raise TrendException("Week statistics is empty")

        return self.data[0].date

    @property
    def stop(self) -> datetime.date:
        if not self.data:
            raise TrendException("Week statistics is empty")

        return self.data[-1].date

    @property
    def average(self) -> Decimal:
        pass

    @property
    def median(self) -> int:
        pass

    @property
    def total(self) -> int:
        pass

    @property
    def max(self) -> DayStatistics:
        pass

    @property
    def min(self) -> DayStatistics:
        pass


@dataclass
class WeekBorder:
    start: datetime.date
    stop: datetime.date

    def __init__(self,
                 start: datetime.date,
                 stop: datetime.date) -> None:
        if (stop - start).days != 6:
            raise TrendException(f"Wrong week got: [{start}; {stop}]")

        self.start = start
        self.stop = stop

    def format(self) -> str:
        return f"{self.start.strftime(settings.DATE_FORMAT)}_" \
               f"{self.stop.strftime(settings.DATE_FORMAT)}"

    def __str__(self) -> str:
        return f"[{self.start.strftime(settings.DATE_FORMAT)}; " \
               f"{self.stop.strftime(settings.DATE_FORMAT)}]"


class Trend(NamedTuple):
    last_week: WeekBorder
    current_week: WeekBorder
    last_week_value: Decimal
    current_week_value: Decimal
    trend: Decimal

    @property
    def weeks(self) -> list[str]:
        return [
            self.last_week.format(),
            self.current_week.format()
        ]

    @property
    def values(self) -> list[Decimal]:
        return [
            self.last_week_value,
            self.current_week_value
        ]

    def __str__(self) -> str:
        return f"{self.last_week}: {self.last_week_value}\n" \
               f"{self.current_week}: {self.current_week_value}\n" \
               f"Trend: {self.trend}"


def _get_last_week_range() -> WeekBorder:
    now = datetime.date.today()
    weekday = now.weekday()

    start = now - datetime.timedelta(days=weekday + 7)
    stop = start + datetime.timedelta(days=weekday)

    return WeekBorder(start=start, stop=stop)


def _get_current_week_range() -> WeekBorder:
    now = datetime.date.today()
    weekday = now.weekday()

    start = now - datetime.timedelta(days=weekday)

    return WeekBorder(start=start, stop=now)


async def _get_week_read_pages(week: WeekBorder) -> Decimal:
    logger.debug("Getting week='%s' read pages", week)
    start, stop = week

    stmt = sa.select(sa.func.sum(models.ReadingLog.c.count)) \
        .where(sa.func.date(models.ReadingLog.c.date) >= start) \
        .where(sa.func.date(models.ReadingLog.c.date) <= stop)

    async with database.session() as ses:
        value = await ses.scalar(stmt) or 0

    logger.debug("Week='%s' read pages got", week)
    return Decimal(value)


async def _get_week_inserted_notes(week: WeekBorder) -> Decimal:
    logger.debug("Getting week='%s' inserted notes count", week)
    start, stop = week

    stmt = sa.select(sa.func.count(models.Notes.c.note_id)) \
        .where(sa.func.date(models.Notes.c.added_at) >= start) \
        .where(sa.func.date(models.Notes.c.added_at) <= stop)

    async with database.session() as ses:
        value = await ses.scalar(stmt) or 0

    logger.debug("Week='%s' inserted notes count got", week)
    return Decimal(value)


def _calculate_trend(*,
                     last_week_value: Decimal,
                     current_week_value: Decimal,
                     current_week: WeekBorder,
                     last_week: WeekBorder) -> Trend:
    trend_percent = Decimal(0)
    if last_week_value:
        trend = (current_week_value - last_week_value) / last_week_value
        trend_percent: Decimal = round(trend * 100, 2) # type: ignore

    return Trend(
        current_week=current_week,
        last_week=last_week,
        last_week_value=last_week_value,
        current_week_value=current_week_value,
        trend=trend_percent
    )


async def get_read_pages_trend() -> Trend:
    logger.info("Getting read pages trend")

    last_week, current_week = _get_last_week_range(), _get_current_week_range()

    last_week_read_pages_task = asyncio.create_task(_get_week_read_pages(last_week))
    current_week_read_pages_task = asyncio.create_task(_get_week_read_pages(current_week))

    await last_week_read_pages_task
    await current_week_read_pages_task

    trend = _calculate_trend(
        last_week_value=last_week_read_pages_task.result(),
        current_week_value=current_week_read_pages_task.result(),
        current_week=current_week,
        last_week=last_week
    )

    logger.info("Reading pages trend got")
    return trend


async def get_inserted_notes_trend() -> Trend:
    logger.info("Getting inserted notes trend")

    last_week, current_week = _get_last_week_range(), _get_current_week_range()

    last_week_inserted_notes_task = asyncio.create_task(_get_week_inserted_notes(last_week))
    current_week_inserted_notes_task = asyncio.create_task(_get_week_inserted_notes(current_week))

    await last_week_inserted_notes_task
    await current_week_inserted_notes_task

    trend = _calculate_trend(
        last_week_value=last_week_inserted_notes_task.result(),
        current_week_value=current_week_inserted_notes_task.result(),
        current_week=current_week,
        last_week=last_week
    )

    logger.info("Inserted notes trend got")
    return trend
