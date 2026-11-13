import base64
import datetime
import types
from collections.abc import Iterator

import matplotlib as mpl
import matplotlib.pyplot as plt
import pytest

from tracker.system import trends


mpl.use("Agg")


@pytest.fixture(autouse=True)
def clean_matplotlib_state() -> Iterator[None]:
    plt.close("all")
    yield
    plt.close("all")
    plt.style.use("default")


def frozen_datetime_module(now: datetime.datetime) -> types.SimpleNamespace:
    """A stand-in for the `datetime` module whose `datetime.now()` is pinned."""

    class FrozenDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz: datetime.tzinfo | None = None) -> datetime.datetime:
            return now.replace(tzinfo=tz)

    return types.SimpleNamespace(
        datetime=FrozenDatetime,
        date=datetime.date,
        time=datetime.time,
        timedelta=datetime.timedelta,
        UTC=datetime.UTC,
    )


def decode_svg(image: str) -> str:
    return base64.b64decode(image, validate=True).decode("utf-8")


def build_statistics(
    amounts: list[int],
    *,
    start: datetime.date = datetime.date(2024, 1, 1),
) -> trends.SpanStatistics:
    days = [
        trends.DayStatistics(date=start + datetime.timedelta(days=shift), amount=amount)
        for shift, amount in enumerate(amounts)
    ]
    return trends.SpanStatistics(data=days, span_size=len(amounts))
