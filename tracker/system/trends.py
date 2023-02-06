import base64
import datetime
import statistics
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
class SpanStatistics:
    data: list[DayStatistics]

    def __init__(self,
                 days: Sequence[tuple[datetime.date, int]],
                 *,
                 span_size: int) -> None:
        if len(days) != span_size:
            raise TrendException(
                f"A span should contains exactly {span_size} days, but {len(days)} found")

        self.data = [
            DayStatistics(date=date, amount=amount)
            for date, amount in days
        ]
        self.span_size = span_size

    @property
    def start(self) -> datetime.date:
        if not self.data:
            raise TrendException("Span statistics is empty")

        return self.data[0].date

    @property
    def stop(self) -> datetime.date:
        if not self.data:
            raise TrendException("Span statistics is empty")

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
        value = Decimal(self.total) / self.span_size
        return round(value, 2)

    @property
    def median(self) -> float:
        return round(statistics.median(self.values), 2)

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
class TimeSpan:
    start: datetime.date
    stop: datetime.date

    def __init__(self,
                 start: datetime.date,
                 stop: datetime.date,
                 span_size: int) -> None:
        # - 1 because the border is included to the range
        if (stop - start).days != span_size - 1:
            raise TrendException(f"Wrong span got: [{start}; {stop}]")

        self.start = start
        self.stop = stop

    def format(self) -> str:
        return f"{self.start.strftime(settings.DATE_FORMAT)}_" \
               f"{self.stop.strftime(settings.DATE_FORMAT)}"

    def __str__(self) -> str:
        return f"[{self.start.strftime(settings.DATE_FORMAT)}; " \
               f"{self.stop.strftime(settings.DATE_FORMAT)}]"


def _get_span(size: int) -> TimeSpan:
    now = datetime.date.today()
    start = now - datetime.timedelta(days=size - 1)

    return TimeSpan(start=start, stop=now, span_size=size)


def _iterate_over_span(span: TimeSpan,
                       *,
                       size: int) -> Generator[datetime.date, None, None]:
    start = span.start
    for day in range(size):
        yield start + datetime.timedelta(days=day)


async def _calculate_span_reading_statistics(span: TimeSpan) -> dict[datetime.date, int]:
    logger.debug("Calculating span reading statistics")

    stmt = sa.select([models.ReadingLog.c.date,
                      models.ReadingLog.c.count])\
        .where(models.ReadingLog.c.date >= span.start)\
        .where(models.ReadingLog.c.date <= span.stop)

    async with database.session() as ses:
        rows = (await ses.execute(stmt)).all()

    logger.debug("Span reading statistics calculated")

    return {
        row.date.date(): row.count
        for row in rows
    }


async def _calculate_span_notes_statistics(span: TimeSpan) -> dict[datetime.date, int]:
    logger.debug("Calculating span notes statistics")

    stmt = sa.select([sa.func.date(models.Notes.c.added_at).label('date'),
                      sa.func.count(models.Notes.c.note_id)]) \
        .group_by(sa.func.date(models.Notes.c.added_at)) \
        .where(sa.func.date(models.Notes.c.added_at) >= span.start) \
        .where(sa.func.date(models.Notes.c.added_at) <= span.stop)

    async with database.session() as ses:
        rows = (await ses.execute(stmt)).all()

    logger.debug("Span notes statistics calculated")

    return {
        row.date: row.count
        for row in rows
    }


def _get_span_statistics(*,
                         stat: dict[datetime.date, int],
                         span: TimeSpan,
                         span_size: int) -> SpanStatistics:
    logger.debug("Getting span statistics of size = %s", span_size)

    days = [
        DayStatistics(date=date, amount=stat.get(date, 0))
        for date in _iterate_over_span(span, size=span_size)
    ]

    logger.debug("Span statistics got")
    return SpanStatistics(days=days, span_size=span_size)


async def get_span_reading_statistics(*,
                                      span_size: int) -> SpanStatistics:
    span = _get_span(span_size)
    stat = await _calculate_span_reading_statistics(span=span)

    return _get_span_statistics(
        stat=stat, span=span, span_size=span_size)


async def get_span_notes_statistics(*,
                                    span_size: int) -> SpanStatistics:
    span = _get_span(span_size)
    stat = await _calculate_span_notes_statistics(span=span)

    return _get_span_statistics(
        stat=stat, span=span, span_size=span_size)


def _create_graphic(*,
                    stat: SpanStatistics,
                    title: str = 'Total items completed') -> str:
    logger.debug("Creating graphic started")

    fig, ax = plt.subplots(figsize=(12, 10))
    bar = ax.barh(stat.days, stat.values, edgecolor="white")
    ax.bar_label(bar)

    xlim = -0.5, int(stat.max.amount * 1.2) or 100

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


async def create_reading_graphic(stat: SpanStatistics | None = None,
                                 *,
                                 span_size: int = 7) -> str:
    logger.info("Creating reading graphic")

    stat = stat or await get_span_reading_statistics(span_size=span_size)
    return _create_graphic(
        stat=stat,
        title='Total pages read'
    )


async def create_notes_graphic(stat: SpanStatistics | None = None,
                               *,
                               span_size: int = 7) -> str:
    logger.info("Creating notes graphic")

    stat = stat or await get_span_notes_statistics(span_size=span_size)
    return _create_graphic(
        stat=stat,
        title='Total notes inserted'
    )
