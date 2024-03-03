import asyncio
import base64
import datetime
import statistics
from collections.abc import Generator, Sequence
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from typing import Any, NamedTuple

import matplotlib.pyplot as plt
import sqlalchemy.sql as sa

from tracker.common import database, settings
from tracker.common.logger import logger
from tracker.models import enums, models
from tracker.system import schemas


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

    def __init__(
        self, days: Sequence[tuple[datetime.date, int]], *, span_size: int,
    ) -> None:
        if len(days) != span_size:
            raise TrendException(
                f"A span should contains exactly {span_size} days, but {len(days)} found",
            )

        self.data = [DayStatistics(date=date, amount=amount) for date, amount in days]
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
        return [day.format() for day in self.data]

    @property
    def values(self) -> list[int]:
        return [day.amount for day in self.data]

    @property
    def mean(self) -> Decimal:
        value = Decimal(self.total) / self.span_size
        return round(value, 2)

    @property
    def median(self) -> float:
        return round(statistics.median(self.values), 2)

    @property
    def total(self) -> int:
        return sum(day.amount for day in self.data)

    @property
    def max(self) -> DayStatistics:
        return max(self.data, key=lambda day: day.amount)

    @property
    def min(self) -> DayStatistics:
        data = filter(lambda day: day.amount != 0, self.data)
        try:
            return min(data, key=lambda day: day.amount)
        except ValueError:
            return self.data[0]

    @property
    def zero_days(self) -> int:
        return sum(1 for day in self.data if day.amount == 0)

    @property
    def lost_pages(self) -> int:
        return round(self.zero_days * self.mean)

    @property
    def would_be_total(self) -> int:
        return self.total + self.lost_pages

    def dump(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "median": self.median,
            "mean": self.mean,
            "lost_count": self.lost_pages,
            "zero_days": self.zero_days,
            "would_be_total": self.would_be_total,
        }

    def __str__(self) -> str:
        return "\n".join(str(day) for day in self.data)


@dataclass
class TimeSpan:
    start: datetime.date
    stop: datetime.date

    def __init__(self, start: datetime.date, stop: datetime.date, span_size: int) -> None:
        if span_size < 0:
            raise TrendException(f"Negative span size passed: {span_size}")
        if start > stop:
            raise TrendException(f"Start is better than stop: {start} > {stop}")

        # + 1 because the border is included to the range
        if (stop - start).days + 1 != span_size:
            raise TrendException(f"Wrong span got: [{start}; {stop}]")

        self.start = start
        self.stop = stop

    def format(self) -> str:
        return (
            f"{self.start.strftime(settings.DATE_FORMAT)}_"
            f"{self.stop.strftime(settings.DATE_FORMAT)}"
        )

    def __str__(self) -> str:
        return (
            f"[{self.start.strftime(settings.DATE_FORMAT)}; "
            f"{self.stop.strftime(settings.DATE_FORMAT)}]"
        )


@dataclass
class _MaterialAnalytics:
    """Analytics grouped by material type."""

    stats: dict[enums.MaterialTypesEnum, int]
    total: int


@dataclass
class _RepeatAnalytics:
    repeats_count: int
    unique_materials_count: int


@dataclass
class SpanAnalysis:
    reading: SpanStatistics
    notes: SpanStatistics
    materials_analytics: _MaterialAnalytics
    reading_analytics: _MaterialAnalytics
    repeat_analytics: _RepeatAnalytics


def _get_span(size: int) -> TimeSpan:
    now = database.utcnow().date()
    start = now - datetime.timedelta(days=size - 1)

    return TimeSpan(start=start, stop=now, span_size=size)


def _iterate_over_span(
    span: TimeSpan, *, size: int,
) -> Generator[datetime.date, None, None]:
    start = span.start
    for day in range(size):
        yield start + datetime.timedelta(days=day)


async def _calculate_span_reading_statistics(span: TimeSpan) -> dict[datetime.date, int]:
    logger.debug("Calculating span reading statistics")

    stmt = (
        sa.select(
            models.ReadingLog.c.date, sa.func.sum(models.ReadingLog.c.count).label("cnt"),
        )
        .where(models.ReadingLog.c.date >= span.start)
        .where(models.ReadingLog.c.date <= span.stop)
        .group_by(models.ReadingLog.c.date)
    )

    async with database.session() as ses:
        rows = (await ses.execute(stmt)).all()

    logger.debug("Span reading statistics calculated")

    return {row.date: row.cnt for row in rows}


async def _calculate_span_notes_statistics(span: TimeSpan) -> dict[datetime.date, int]:
    logger.debug("Calculating span notes statistics")

    stmt = (
        sa.select(
            sa.func.date(models.Notes.c.added_at).label("date"),
            sa.func.count(models.Notes.c.note_id).label("cnt"),
        )
        .group_by(sa.func.date(models.Notes.c.added_at))
        .where(~models.Notes.c.is_deleted)
        .where(sa.func.date(models.Notes.c.added_at) >= span.start)
        .where(sa.func.date(models.Notes.c.added_at) <= span.stop)
    )

    async with database.session() as ses:
        rows = (await ses.execute(stmt)).all()

    logger.debug("Span notes statistics calculated")

    return {row.date: row.cnt for row in rows}


def _get_span_statistics(
    *, stat: dict[datetime.date, int], span: TimeSpan, span_size: int,
) -> SpanStatistics:
    logger.debug("Getting span statistics of size = %s", span_size)

    days = [
        DayStatistics(date=date, amount=stat.get(date, 0))
        for date in _iterate_over_span(span, size=span_size)
    ]

    logger.debug("Span statistics got")
    return SpanStatistics(days=days, span_size=span_size)


async def get_span_reading_statistics(*, span_size: int) -> SpanStatistics:
    span = _get_span(span_size)
    stat = await _calculate_span_reading_statistics(span=span)

    return _get_span_statistics(stat=stat, span=span, span_size=span_size)


async def get_span_notes_statistics(*, span_size: int) -> SpanStatistics:
    span = _get_span(span_size)
    stat = await _calculate_span_notes_statistics(span=span)

    return _get_span_statistics(stat=stat, span=span, span_size=span_size)


async def get_span_analytics(__span: schemas.GetSpanReportRequest) -> SpanAnalysis:
    """Calculate both reading and notes statistics."""
    size = __span.size
    span = TimeSpan(start=__span.start, stop=__span.stop, span_size=size)

    async with asyncio.TaskGroup() as tg:
        reading_stats_task = tg.create_task(_calculate_span_reading_statistics(span))
        notes_stats_task = tg.create_task(_calculate_span_notes_statistics(span))
        material_analytics_task = tg.create_task(_materials_analytics(span))
        reading_analytics_task = tg.create_task(_reading_analytics(span))
        repeat_analytics_task = tg.create_task(_get_repeats_count(span))

    reading_stats = _get_span_statistics(
        stat=reading_stats_task.result(), span=span, span_size=size,
    )
    notes_stats = _get_span_statistics(
        stat=notes_stats_task.result(), span=span, span_size=size,
    )

    return SpanAnalysis(
        reading=reading_stats,
        notes=notes_stats,
        materials_analytics=material_analytics_task.result(),
        reading_analytics=reading_analytics_task.result(),
        repeat_analytics=repeat_analytics_task.result(),
    )


async def _materials_analytics(span: TimeSpan) -> _MaterialAnalytics:
    """Get how many materials was completed in the span, group them by material types."""
    stmt = (
        sa.select(
            models.Materials.c.material_type,
            sa.func.count(models.Materials.c.material_id.distinct()).label("cnt"),
        )
        .join(models.Statuses)
        .where(models.Statuses.c.completed_at >= span.start)
        .where(models.Statuses.c.completed_at <= span.stop)
        .group_by(models.Materials.c.material_type)
    )

    async with database.session() as ses:
        res = (await ses.execute(stmt)).all()
    stats = {r.material_type: r.cnt for r in res}

    return _MaterialAnalytics(stats=stats, total=sum(stats.values()))


async def _reading_analytics(span: TimeSpan) -> _MaterialAnalytics:
    """Get how many pages were read in the span, group them by material types."""
    stmt = (
        sa.select(
            models.Materials.c.material_type,
            sa.func.sum(models.ReadingLog.c.count).label("cnt"),
        )
        .join(models.ReadingLog)
        .where(models.ReadingLog.c.date >= span.start)
        .where(models.ReadingLog.c.date <= span.stop)
        .group_by(models.Materials.c.material_type)
    )

    async with database.session() as ses:
        res = (await ses.execute(stmt)).all()
    stats = {r.material_type: r.cnt for r in res}

    return _MaterialAnalytics(stats=stats, total=sum(stats.values()))


async def _get_repeats_count(span: TimeSpan) -> _RepeatAnalytics:
    stmt = (
        sa.select(
            sa.func.count(1).label("cnt"),  # type: ignore[arg-type]
            sa.func.count(models.Repeats.c.material_id.distinct()).label("ucnt"),
        )
        .select_from(models.Repeats)
        .where(sa.func.date(models.Repeats.c.repeated_at) >= span.start)
        .where(sa.func.date(models.Repeats.c.repeated_at) <= span.stop)
    )
    # TODO: convert datetime to date where its required

    async with database.session() as ses:
        res = (await ses.execute(stmt)).mappings().one_or_none()

    if res:
        return _RepeatAnalytics(repeats_count=res.cnt, unique_materials_count=res.ucnt)
    return _RepeatAnalytics(0, 0)


def _get_colors(
    completion_dates: dict[Any, datetime.datetime] | None, days: list[str],
) -> list[str] | None:
    """Mark the days when a material completed with green."""
    if not completion_dates:
        return None

    dates = {
        date.date().strftime(settings.DATE_FORMAT) for date in completion_dates.values()
    }
    return ["green" if day in dates else "steelblue" for day in days]


def _create_graphic(
    *,
    stat: SpanStatistics,
    title: str = "Total items completed",
    show_mean_line: bool = True,
    completion_dates: dict[Any, datetime.datetime] | None = None,
) -> str:
    logger.debug("Creating graphic started")

    days = stat.days
    # set completion dates color to green
    colors = _get_colors(completion_dates, days)

    fig, ax = plt.subplots(figsize=(12, 10))
    bar = ax.barh(days, stat.values, edgecolor="white", color=colors)
    ax.bar_label(bar)

    if show_mean_line:
        line = plt.axvline(x=float(stat.mean), color="black", linestyle="-")
        line.set_label(f"Mean {stat.mean} items")

    xlim = -0.5, int(stat.max.amount * 1.2) or 100

    ax.set_title(title)
    ax.set_xlabel("Items count")
    ax.set_ylabel("Date")
    ax.set_xlim(xlim)
    if show_mean_line:
        ax.legend()
    plt.gca().invert_yaxis()

    tmpbuf = BytesIO()
    fig.savefig(tmpbuf, format="svg")

    image = base64.b64encode(tmpbuf.getvalue()).decode("utf-8")

    logger.debug("Creating graphic completed")
    return image


async def create_reading_graphic(
    stat: SpanStatistics | None = None,
    *,
    span_size: int = 7,
    completion_dates: dict[Any, datetime.datetime] | None = None,
) -> str:
    logger.info("Creating reading graphic")

    stat = stat or await get_span_reading_statistics(span_size=span_size)
    return _create_graphic(
        stat=stat, title="Total pages read", completion_dates=completion_dates,
    )


async def create_notes_graphic(
    stat: SpanStatistics | None = None, *, span_size: int = 7,
) -> str:
    logger.info("Creating notes graphic")

    stat = stat or await get_span_notes_statistics(span_size=span_size)
    return _create_graphic(stat=stat, title="Total notes inserted")
