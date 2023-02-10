import datetime

import pytest

from tracker.common import settings
from tracker.system import trends


@pytest.mark.parametrize(
    'size', (
        1, 0, 6, 7, 34
    )
)
def test_get_span(size):
    span = trends._get_span(size)
    assert (span.stop - span.start).days + 1 == size

    assert span.stop == datetime.date.today()
    assert span.start == span.stop - datetime.timedelta(days=size - 1)


@pytest.mark.parametrize(
    'size', (
        1, 0, 6, 7, 34
    )
)
def test_span_methods(size):
    span = trends._get_span(size)

    today = datetime.date.today()
    start = today - datetime.timedelta(days=size - 1)

    assert span.format() == f"{start.strftime(settings.DATE_FORMAT)}_{today.strftime(settings.DATE_FORMAT)}"
    assert str(span) == f"[{start.strftime(settings.DATE_FORMAT)}; {today.strftime(settings.DATE_FORMAT)}]"
