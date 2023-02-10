import datetime

import pytest

from tracker.common import settings
from tracker.system import trends


@pytest.mark.parametrize(
    'size', (
        1, 6, 7, 34
    )
)
def test_get_span(size):
    span = trends._get_span(size)
    assert (span.stop - span.start).days + 1 == size

    assert span.stop == datetime.date.today()
    assert span.start == span.stop - datetime.timedelta(days=size - 1)


@pytest.mark.parametrize(
    'size', (
        1, 6, 7, 34
    )
)
def test_span_methods(size):
    span = trends._get_span(size)

    today = datetime.date.today()
    start = today - datetime.timedelta(days=size - 1)

    assert span.format() == f"{start.strftime(settings.DATE_FORMAT)}_{today.strftime(settings.DATE_FORMAT)}"
    assert str(span) == f"[{start.strftime(settings.DATE_FORMAT)}; {today.strftime(settings.DATE_FORMAT)}]"


@pytest.mark.parametrize(
    'start,size', (
        (datetime.date(2023, 1, 1), 10),
        (datetime.date(2023, 1, 1), 5),
        (datetime.date(2023, 1, 1), 1),
    )
)
def test_iterate_over_span(start, size):
    stop = start + datetime.timedelta(days=size - 1)
    span = trends.TimeSpan(start=start, stop=stop, span_size=size)

    result = [date for date in trends._iterate_over_span(span, size=size)]

    assert len(result) == size
    for index, day in enumerate(range(size)):
        assert result[index] == start + datetime.timedelta(days=day)
