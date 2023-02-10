import datetime

import pytest

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
