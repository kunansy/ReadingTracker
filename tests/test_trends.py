import datetime
from decimal import Decimal

import pytest
import sqlalchemy.sql as sa

from tracker.common import database, settings
from tracker.models import models
from tracker.system import trends


@pytest.mark.parametrize("size", (1, 6, 7, 34))
def test_get_span(size):
    span = trends._get_span(size)
    assert (span.stop - span.start).days + 1 == size

    assert span.stop == datetime.date.today()
    assert span.start == span.stop - datetime.timedelta(days=size - 1)


@pytest.mark.parametrize("size", (1, 6, 7, 34))
def test_span_methods(size):
    span = trends._get_span(size)

    today = datetime.date.today()
    start = today - datetime.timedelta(days=size - 1)

    assert (
        span.format()
        == f"{start.strftime(settings.DATE_FORMAT)}_{today.strftime(settings.DATE_FORMAT)}"  # noqa
    )
    assert (
        str(span)
        == f"[{start.strftime(settings.DATE_FORMAT)}; {today.strftime(settings.DATE_FORMAT)}]"  # noqa
    )


@pytest.mark.parametrize(
    "start,size",
    (
        (datetime.date(2023, 1, 1), 10),
        (datetime.date(2023, 1, 1), 5),
        (datetime.date(2023, 1, 1), 1),
    ),
)
def test_iterate_over_span(start, size):
    stop = start + datetime.timedelta(days=size - 1)
    span = trends.TimeSpan(start=start, stop=stop, span_size=size)

    result = [date for date in trends._iterate_over_span(span, size=size)]

    assert len(result) == size
    for index, day in enumerate(range(size)):
        assert result[index] == start + datetime.timedelta(days=day)


@pytest.mark.parametrize(
    "start,stop,size",
    (
        (datetime.date(2023, 1, 7), datetime.date(2023, 1, 7), 1),
        (datetime.date(2023, 1, 7), datetime.date(2023, 1, 10), 4),
        (datetime.date(2023, 1, 7), datetime.date(2023, 2, 7), 32),
        (datetime.date(2022, 8, 1), datetime.date(2022, 11, 1), 93),
    ),
)
async def test_calculate_span_reading_statistics(start, stop, size):
    span = trends.TimeSpan(start=start, stop=stop, span_size=size)
    result = await trends._calculate_span_reading_statistics(span=span)

    stmt = (
        sa.select(models.ReadingLog.c.date, sa.func.sum(models.ReadingLog.c.count))
        .where(models.ReadingLog.c.date >= span.start)
        .where(models.ReadingLog.c.date <= span.stop)
        .group_by(models.ReadingLog.c.date)
    )

    async with database.session() as ses:
        expected = {date: count for date, count in (await ses.execute(stmt)).all()}

    assert result == expected


@pytest.mark.parametrize(
    "start,stop,size",
    (
        (datetime.date(2023, 1, 7), datetime.date(2023, 1, 7), 1),
        (datetime.date(2023, 1, 7), datetime.date(2023, 1, 10), 4),
        (datetime.date(2023, 1, 7), datetime.date(2023, 2, 7), 32),
        (datetime.date(2022, 8, 1), datetime.date(2022, 11, 1), 93),
    ),
)
async def test_calculate_span_notes_statistics(start, stop, size):
    span = trends.TimeSpan(start=start, stop=stop, span_size=size)
    result = await trends._calculate_span_notes_statistics(span=span)

    stmt = (
        sa.select(
            sa.func.date(models.Notes.c.added_at).label("date"),
            sa.func.count(models.Notes.c.note_id),
        )
        .group_by(sa.func.date(models.Notes.c.added_at))
        .where(sa.func.date(models.Notes.c.added_at) >= span.start)
        .where(sa.func.date(models.Notes.c.added_at) <= span.stop)
    )

    async with database.session() as ses:
        expected = {date: count for date, count in (await ses.execute(stmt)).all()}

    assert result == expected


@pytest.mark.parametrize(
    "start,stop,size",
    (
        (datetime.date(2023, 1, 7), datetime.date(2023, 1, 7), 1),
        (datetime.date(2023, 1, 7), datetime.date(2023, 1, 10), 4),
        (datetime.date(2023, 1, 7), datetime.date(2023, 2, 7), 32),
        (datetime.date(2022, 8, 1), datetime.date(2022, 11, 1), 93),
    ),
)
async def test_get_span_statistics(start, stop, size):
    span = trends.TimeSpan(start=start, stop=stop, span_size=size)
    stat = await trends._calculate_span_reading_statistics(span=span)

    result = trends._get_span_statistics(stat=stat, span=span, span_size=size)
    values = list(stat.values())

    assert len(result.data) == size
    total_values = []
    for index, date in enumerate(trends._iterate_over_span(span, size=size)):
        assert result.data[index].date == date
        assert result.data[index].amount == stat.get(date, 0)
        assert result.data[index].format() == date.strftime(settings.DATE_FORMAT)
        assert (
            str(result.data[index])
            == f"{date.strftime(settings.DATE_FORMAT)}: {stat.get(date, 0)}"
        )
        total_values += [stat.get(date, 0)]
    total_values.sort()

    assert result.start == start
    assert result.stop == stop
    assert result.span_size == size
    assert result.days == [
        day.strftime(settings.DATE_FORMAT)
        for day in trends._iterate_over_span(span, size=size)
    ]
    assert sum(result.values) == sum(values)
    assert result.mean == round(sum(values) / Decimal(len(total_values)), 2)

    if (length := len(total_values)) % 2:
        expected_median = total_values[length // 2]
    else:
        expected_median = (total_values[length // 2 - 1] + total_values[length // 2]) / 2

    assert result.median == expected_median
    assert result.total == sum(values)

    assert result.max.amount == max(values)
    if result.min.amount != 0:
        assert result.min.amount == min(values)

    assert result.zero_days == (span.stop - span.start).days + 1 - len(stat)


@pytest.mark.parametrize("size", (1, 7, 14, 62, 180))
async def test_get_span_reading_statistics(size):
    result = await trends.get_span_reading_statistics(span_size=size)

    stop = datetime.date.today()
    start = stop - datetime.timedelta(days=size - 1)
    span = trends.TimeSpan(start=start, stop=stop, span_size=size)

    assert result.start == start
    assert result.stop == stop
    assert result.span_size == size

    stat = await trends._calculate_span_reading_statistics(span=span)
    expected = trends._get_span_statistics(stat=stat, span=span, span_size=size)

    assert result == expected


@pytest.mark.parametrize("size", (1, 7, 14, 62, 180))
async def test_get_span_notes_statistics(size):
    result = await trends.get_span_notes_statistics(span_size=size)

    stop = datetime.date.today()
    start = stop - datetime.timedelta(days=size - 1)
    span = trends.TimeSpan(start=start, stop=stop, span_size=size)

    assert result.start == start
    assert result.stop == stop
    assert result.span_size == size

    stat = await trends._calculate_span_notes_statistics(span=span)
    expected = trends._get_span_statistics(stat=stat, span=span, span_size=size)

    assert result == expected


@pytest.mark.parametrize("size", (1, 7, 14, 62, 180))
async def test_get_span_completed_materials_statistics(size):
    result = await trends.get_span_completed_materials_statistics(span_size=size)

    stop = datetime.date.today()
    start = stop - datetime.timedelta(days=size - 1)
    span = trends.TimeSpan(start=start, stop=stop, span_size=size)

    assert result.start == start
    assert result.stop == stop
    assert result.span_size == size

    stat = await trends._calculate_span_completed_materials_statistics(span=span)
    expected = trends._get_span_statistics(stat=stat, span=span, span_size=size)

    assert result == expected


@pytest.mark.parametrize("size", (1, 7, 14, 62, 180))
async def test_create_reading_graphic(size):
    stat = await trends.get_span_reading_statistics(span_size=size)
    result = trends.create_reading_graphic(stat)

    assert result


@pytest.mark.parametrize("size", (1, 7, 14, 62, 180))
async def test_create_notes_graphic(size):
    stat = await trends.get_span_notes_statistics(span_size=size)
    result = trends.create_notes_graphic(stat)

    assert result


@pytest.mark.parametrize("size", (1, 5, 7))
def test_span_statistics_init_exception(size):
    with pytest.raises(trends.TrendException) as e:
        trends.SpanStatistics(data=[], span_size=size)

    assert str(e.value) == f"Wrong span size: expected={size}, found=0"


def test_span_statistics_empty_start():
    stat = trends.SpanStatistics(data=[], span_size=0)
    with pytest.raises(trends.TrendException) as e:
        stat.start  # noqa

    assert str(e.value) == "Span statistics is empty"


def test_span_statistics_empty_stop():
    stat = trends.SpanStatistics(data=[], span_size=0)
    with pytest.raises(trends.TrendException) as e:
        stat.stop  # noqa

    assert str(e.value) == "Span statistics is empty"


def test_time_span_negative_size():
    with pytest.raises(trends.TrendException) as e:
        trends.TimeSpan(start=datetime.date.today(), stop=datetime.date.today(), span_size=-1)

    assert str(e.value) == "Wrong span got: [2024-04-29; 2024-04-29; -1]"


def test_time_span_start_better_stop():
    with pytest.raises(trends.TrendException) as e:
        trends.TimeSpan(start=datetime.date(1970, 1, 2), stop=datetime.date(1970, 1, 1), span_size=1)

    assert str(e.value).startswith("Start is better than stop")


def test_time_span_wrong_span_size():
    today = datetime.date.today()
    with pytest.raises(trends.TrendException) as e:
        trends.TimeSpan(start=today - datetime.timedelta(days=1), stop=today, span_size=1)

    assert str(e.value).startswith("Wrong span got")
