import base64
import datetime
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from typing import NamedTuple, Sequence, Generator

import matplotlib.pyplot as plt
import sqlalchemy.sql as sa

from tracker.common import database, settings
from tracker.common.log import logger
from tracker.models import models


class TrendException(database.DatabaseException):
    pass


class DayStatistics(NamedTuple):
    date: datetime.date
    amount: int

    def format(self) -> str:
        return self.date.strftime(settings.DATE_FORMAT)

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
    def days(self) -> list[str]:
        return [
            day.format()
            for day in self.data
        ]

    @property
    def values(self) -> list[int]:
        return [
            day.amount
            for day in self.data
        ]

    @property
    def mean(self) -> Decimal:
        value = Decimal(self.total) / 7
        return round(value, 2)

    @property
    def median(self) -> int:
        sorted_days = sorted(self.data, key=lambda day: day.amount)
        return sorted_days[3].amount

    @property
    def total(self) -> int:
        return sum(
            day.amount
            for day in self.data
        )

    @property
    def max(self) -> DayStatistics:
        return max(
            self.data,
            key=lambda day: day.amount
        )

    @property
    def min(self) -> DayStatistics:
        return min(
            self.data,
            key=lambda day: day.amount
        )

    @property
    def zero_count(self) -> int:
        return sum(
            1
            for day in self.data
            if day.amount == 0
        )

    def __str__(self) -> str:
        return '\n'.join(str(day) for day in self.data)


@dataclass
class WeekBorder:
    start: datetime.date
    stop: datetime.date

    def __init__(self,
                 start: datetime.date,
                 stop: datetime.date) -> None:
        # 6 because the border is included to the range
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


def _get_week_range() -> WeekBorder:
    now = datetime.date.today()
    start = now - datetime.timedelta(days=6)

    return WeekBorder(start=start, stop=now)


def _iterate_over_week(week: WeekBorder) -> Generator[datetime.date, None, None]:
    start = week.start
    for day in range(7):
        yield start + datetime.timedelta(days=day)


async def _calculate_week_reading_statistics(week: WeekBorder) -> dict[datetime.date, int]:
    logger.debug("Calculating week reading statistics")

    stmt = sa.select([models.ReadingLog.c.date,
                      models.ReadingLog.c.count])\
        .where(models.ReadingLog.c.date >= week.start)\
        .where(models.ReadingLog.c.date <= week.stop)

    async with database.session() as ses:
        rows = (await ses.execute(stmt)).all()

    logger.debug("Week reading statistics calculated")

    return {
        row.date.date(): row.count
        for row in rows
    }


async def _calculate_week_notes_statistics(week: WeekBorder) -> dict[datetime.date, int]:
    logger.debug("Calculating week notes statistics")

    stmt = sa.select([sa.func.date(models.Notes.c.added_at).label('date'),
                      sa.func.count(models.Notes.c.note_id)]) \
        .group_by(sa.func.date(models.Notes.c.added_at)) \
        .where(sa.func.date(models.Notes.c.added_at) >= week.start) \
        .where(sa.func.date(models.Notes.c.added_at) <= week.stop)

    async with database.session() as ses:
        rows = (await ses.execute(stmt)).all()

    logger.debug("Week notes statistics calculated")

    return {
        row.date: row.count
        for row in rows
    }


def _get_week_statistics(*,
                         statistics: dict[datetime.date, int],
                         week: WeekBorder) -> WeekStatistics:
    logger.debug("Getting week statistics")

    days = [
        DayStatistics(date=date, amount=statistics.get(date, 0))
        for date in _iterate_over_week(week)
    ]

    logger.debug("Week statistics got")
    return WeekStatistics(days=days)


async def get_week_reading_statistics() -> WeekStatistics:
    week = _get_week_range()
    statistics = await _calculate_week_reading_statistics(week=week)

    return _get_week_statistics(statistics=statistics, week=week)


async def get_week_notes_statistics() -> WeekStatistics:
    week = _get_week_range()
    statistics = await _calculate_week_notes_statistics(week=week)

    return _get_week_statistics(statistics=statistics, week=week)


def _create_graphic(*,
                    statistics: WeekStatistics,
                    title: str = 'Total items completed') -> str:
    logger.debug("Creating graphic started")

    fig, ax = plt.subplots(figsize=(12, 10))
    bar = ax.barh(statistics.days, statistics.values, edgecolor="white")
    ax.bar_label(bar)

    xlim = -0.5, int(statistics.max.amount * 1.2) or 100

    ax.set_title(title)
    ax.set_xlabel('Items count')
    ax.set_ylabel('Date')
    ax.set_xlim(xlim)
    plt.gca().invert_yaxis()

    tmpbuf = BytesIO()
    fig.savefig(tmpbuf, format='png')

    image = base64.b64encode(tmpbuf.getvalue()).decode('utf-8')

    logger.debug("Creating graphic completed")
    return image


async def create_reading_graphic(statistics: WeekStatistics | None = None) -> str:
    logger.info("Creating reading graphic")

    statistics = statistics or await get_week_reading_statistics()
    return _create_graphic(
        statistics=statistics,
        title='Total pages read'
    )


async def create_notes_graphic(statistics: WeekStatistics | None = None) -> str:
    logger.info("Creating notes graphic")

    statistics = statistics or await get_week_notes_statistics()
    return _create_graphic(
        statistics=statistics,
        title='Total notes inserted'
    )
