import datetime
import decimal
import statistics
from decimal import Decimal

import pytest

from tests.unit.system.conftest import build_statistics
from tracker.common import database
from tracker.system import trends


D = datetime.date


def _day(day: int, amount: int) -> trends.DayStatistics:
    return trends.DayStatistics(date=D(2024, 1, day), amount=amount)


def test_trend_exception_is_a_database_exception():
    assert issubclass(trends.TrendException, database.DatabaseException)


class TestDayStatistics:
    def test_format_is_the_iso_date(self):
        assert _day(5, 10).format() == "2024-01-05"

    @pytest.mark.parametrize(("amount", "expected"), [(0, "2024-01-05: 0"), (42, "2024-01-05: 42")])
    def test_str(self, amount, expected):
        assert str(_day(5, amount)) == expected


class TestSpanStatistics:
    @pytest.mark.parametrize("size", [1, 5, 7])
    def test_span_size_larger_than_data_is_rejected(self, size):
        with pytest.raises(trends.TrendException) as e:
            trends.SpanStatistics(data=[], span_size=size)

        assert str(e.value) == f"Wrong span size: expected={size}, found=0"

    def test_span_size_smaller_than_data_is_rejected(self):
        with pytest.raises(trends.TrendException) as e:
            trends.SpanStatistics(data=[_day(1, 1), _day(2, 2)], span_size=1)

        assert str(e.value) == "Wrong span size: expected=1, found=2"

    def test_start_and_stop_are_the_border_days(self):
        stat = build_statistics([1, 2, 3])

        assert stat.start == D(2024, 1, 1)
        assert stat.stop == D(2024, 1, 3)

    def test_empty_start_raises(self):
        stat = trends.SpanStatistics(data=[], span_size=0)

        with pytest.raises(trends.TrendException) as e:
            stat.start  # noqa: B018

        assert str(e.value) == "Span statistics is empty"

    def test_empty_stop_raises(self):
        stat = trends.SpanStatistics(data=[], span_size=0)

        with pytest.raises(trends.TrendException) as e:
            stat.stop  # noqa: B018

        assert str(e.value) == "Span statistics is empty"

    def test_days_and_values_keep_data_order(self):
        stat = build_statistics([3, 0, 7])

        assert stat.days == ["2024-01-01", "2024-01-02", "2024-01-03"]
        assert stat.values == [3, 0, 7]

    def test_str_lists_every_day(self):
        assert str(build_statistics([3, 0])) == "2024-01-01: 3\n2024-01-02: 0"

    def test_several_days_with_a_zero_day(self):
        stat = build_statistics([1, 2, 3, 0])

        assert stat.total == 6
        assert stat.mean == Decimal("1.50")
        assert stat.median == 1.5
        assert stat.max_record == _day(3, 3)
        assert stat.min_record == _day(1, 1)
        assert stat.zero_days == 1
        assert stat.lost_pages == 2
        assert stat.would_be_total == 8

    def test_all_zero_days(self):
        stat = build_statistics([0, 0, 0])

        assert stat.total == 0
        assert stat.mean == Decimal(0)
        assert stat.median == 0
        assert stat.max_record == _day(1, 0)
        assert stat.min_record == _day(1, 0)
        assert stat.zero_days == 3
        assert stat.lost_pages == 0
        assert stat.would_be_total == 0

    def test_single_day(self):
        stat = build_statistics([5])

        assert stat.total == 5
        assert stat.mean == Decimal(5)
        assert stat.median == 5
        assert stat.max_record == _day(1, 5)
        assert stat.min_record == _day(1, 5)
        assert stat.zero_days == 0
        assert stat.lost_pages == 0
        assert stat.would_be_total == 5

    @pytest.mark.parametrize(
        ("amounts", "mean"),
        [
            ([10, 0, 0], Decimal("3.33")),
            ([2, 0, 0], Decimal("0.67")),
            ([1, 0, 0, 0, 0, 0, 0, 0], Decimal("0.12")),
            ([3, 0, 0, 0, 0, 0, 0, 0], Decimal("0.38")),
        ],
        ids=["rounded-down", "rounded-up", "half-to-even-down", "half-to-even-up"],
    )
    def test_mean_is_rounded_to_two_places(self, amounts, mean):
        assert build_statistics(amounts).mean == mean

    @pytest.mark.parametrize(
        ("amounts", "median"),
        [([5, 1, 3], 3), ([4, 1, 3, 2], 2.5), ([1, 1, 2, 4], 1.5), ([0, 0, 9], 0)],
        ids=["odd", "even", "even-with-duplicates", "mostly-zeros"],
    )
    def test_median(self, amounts, median):
        assert build_statistics(amounts).median == median

    def test_max_record_is_the_first_of_equal_days(self):
        assert build_statistics([1, 7, 7]).max_record == _day(2, 7)

    def test_min_record_skips_zero_days_and_takes_the_first_of_equal_days(self):
        assert build_statistics([0, 4, 2, 2, 0]).min_record == _day(3, 2)

    @pytest.mark.parametrize(
        ("amounts", "lost_pages"),
        [([0, 1], 0), ([0, 3], 2), ([0, 0, 9], 6), ([1, 1], 0)],
        ids=["half-rounds-to-even-0", "half-rounds-to-even-2", "two-zero-days", "no-zero-days"],
    )
    def test_lost_pages_is_zero_days_times_mean(self, amounts, lost_pages):
        assert build_statistics(amounts).lost_pages == lost_pages

    def test_dump(self):
        assert build_statistics([1, 2, 3, 0]).dump() == {
            "total": 6,
            "median": 1.5,
            "mean": Decimal("1.50"),
            "lost_count": 2,
            "zero_days": 1,
            "would_be_total": 8,
        }

    def test_model_dump_includes_computed_fields(self):
        dumped = build_statistics([4]).model_dump()

        day = {"date": D(2024, 1, 1), "amount": 4}
        assert dumped == {
            "data": [day],
            "span_size": 1,
            "mean": Decimal(4),
            "median": 4,
            "total": 4,
            "max_record": day,
            "min_record": day,
            "zero_days": 0,
            "lost_pages": 0,
            "would_be_total": 4,
        }

    def test_empty_span_counters_are_zero(self):
        stat = trends.SpanStatistics(data=[], span_size=0)

        assert stat.total == 0
        assert stat.zero_days == 0
        assert stat.days == []
        assert stat.values == []
        assert str(stat) == ""

    @pytest.mark.parametrize(
        ("attribute", "error"),
        [
            ("mean", decimal.InvalidOperation),
            ("median", statistics.StatisticsError),
            ("max_record", ValueError),
            ("min_record", IndexError),
            ("lost_pages", decimal.InvalidOperation),
            ("would_be_total", decimal.InvalidOperation),
        ],
    )
    def test_empty_span_aggregates_raise_current_behaviour(self, attribute, error):
        stat = trends.SpanStatistics(data=[], span_size=0)

        with pytest.raises(error):
            getattr(stat, attribute)

    def test_empty_span_cannot_be_dumped_current_behaviour(self):
        stat = trends.SpanStatistics(data=[], span_size=0)

        with pytest.raises(statistics.StatisticsError):
            stat.dump()
        with pytest.raises(decimal.InvalidOperation):
            stat.model_dump()

    def test_negative_span_size_is_rejected(self):
        with pytest.raises(trends.TrendException, match="expected=-1, found=0"):
            trends.SpanStatistics(data=[], span_size=-1)


class TestTimeSpan:
    @pytest.mark.parametrize(
        ("start", "stop", "size"),
        [
            (D(2023, 1, 7), D(2023, 1, 7), 1),
            (D(2023, 1, 7), D(2023, 1, 10), 4),
            (D(2023, 1, 7), D(2023, 2, 7), 32),
            (D(2024, 2, 28), D(2024, 3, 1), 3),
            (D(2023, 12, 31), D(2024, 1, 1), 2),
        ],
        ids=["one-day", "four-days", "over-month", "leap-day", "over-year"],
    )
    def test_valid_span(self, start, stop, size):
        span = trends.TimeSpan(start=start, stop=stop, span_size=size)

        assert (span.start, span.stop, span.span_size) == (start, stop, size)

    def test_negative_size_is_rejected(self):
        day = D(2020, 1, 1)

        with pytest.raises(trends.TrendException) as e:
            trends.TimeSpan(start=day, stop=day, span_size=-1)

        assert str(e.value) == "Wrong span got: [2020-01-01; 2020-01-01; -1]"

    @pytest.mark.parametrize("size", [0, 1, 3], ids=["zero", "one-less", "one-more"])
    def test_size_different_from_the_range_is_rejected(self, size):
        with pytest.raises(trends.TrendException) as e:
            trends.TimeSpan(start=D(2024, 1, 1), stop=D(2024, 1, 2), span_size=size)

        assert str(e.value) == f"Wrong span got: [2024-01-01; 2024-01-02; {size}]"

    @pytest.mark.parametrize("size", [0, 1], ids=["size-matching-the-range", "wrong-size"])
    def test_start_after_stop_is_rejected(self, size):
        with pytest.raises(trends.TrendException) as e:
            trends.TimeSpan(start=D(1970, 1, 2), stop=D(1970, 1, 1), span_size=size)

        assert str(e.value) == "Start is better than stop: 1970-01-02 > 1970-01-01"

    @pytest.mark.parametrize("missing", ["start", "stop", "span_size"])
    def test_missing_field_raises_key_error_current_behaviour(self, missing):
        values = {"start": D(2024, 1, 1), "stop": D(2024, 1, 1), "span_size": 1}
        del values[missing]

        with pytest.raises(KeyError, match=missing):
            trends.TimeSpan(**values)

    def test_format(self):
        span = trends.TimeSpan(start=D(2024, 1, 1), stop=D(2024, 1, 7), span_size=7)

        assert span.format() == "2024-01-01_2024-01-07"

    def test_str(self):
        span = trends.TimeSpan(start=D(2024, 1, 1), stop=D(2024, 1, 7), span_size=7)

        assert str(span) == "[2024-01-01; 2024-01-07]"

    def test_iter_yields_every_day_including_borders(self):
        span = trends.TimeSpan(start=D(2024, 2, 28), stop=D(2024, 3, 1), span_size=3)

        assert list(span.iter()) == [D(2024, 2, 28), D(2024, 2, 29), D(2024, 3, 1)]

    def test_iter_of_one_day_span(self):
        span = trends.TimeSpan(start=D(2024, 1, 1), stop=D(2024, 1, 1), span_size=1)

        assert list(span.iter()) == [D(2024, 1, 1)]


class TestGetSpan:
    @pytest.fixture(autouse=True)
    def frozen_clock(self, mocker):
        mocker.patch.object(
            database,
            "utcnow",
            return_value=datetime.datetime(2024, 3, 1, 23, 59, 59),  # noqa: DTZ001
        )

    @pytest.mark.parametrize(
        ("size", "start"),
        [(1, D(2024, 3, 1)), (2, D(2024, 2, 29)), (7, D(2024, 2, 24)), (34, D(2024, 1, 28))],
    )
    def test_span_ends_today_and_has_the_requested_size(self, size, start):
        span = trends._get_span(size)

        assert span == trends.TimeSpan(start=start, stop=D(2024, 3, 1), span_size=size)

    @pytest.mark.parametrize("size", [1, 6, 7, 34])
    def test_span_methods(self, size):
        span = trends._get_span(size)

        start = (D(2024, 3, 1) - datetime.timedelta(days=size - 1)).isoformat()
        assert span.format() == f"{start}_2024-03-01"
        assert str(span) == f"[{start}; 2024-03-01]"

    @pytest.mark.parametrize("size", [0, -1])
    def test_non_positive_size_is_rejected(self, size):
        with pytest.raises(trends.TrendException, match="Start is better than stop"):
            trends._get_span(size)


class TestIterateOverSpan:
    @pytest.mark.parametrize(
        ("start", "size"),
        [(D(2023, 1, 1), 10), (D(2023, 1, 1), 5), (D(2023, 1, 1), 1), (D(2023, 12, 30), 4)],
    )
    def test_yields_size_days_from_the_span_start(self, start, size):
        stop = start + datetime.timedelta(days=size - 1)
        span = trends.TimeSpan(start=start, stop=stop, span_size=size)

        result = list(trends._iterate_over_span(span, size=size))

        assert result == [start + datetime.timedelta(days=day) for day in range(size)]
        assert result[-1] == stop

    def test_zero_size_yields_nothing(self):
        span = trends.TimeSpan(start=D(2023, 1, 1), stop=D(2023, 1, 3), span_size=3)

        assert list(trends._iterate_over_span(span, size=0)) == []

    def test_size_is_not_limited_by_the_span(self):
        span = trends.TimeSpan(start=D(2023, 1, 1), stop=D(2023, 1, 1), span_size=1)

        assert list(trends._iterate_over_span(span, size=2)) == [D(2023, 1, 1), D(2023, 1, 2)]


class TestGetSpanStatistics:
    SPAN = trends.TimeSpan(start=D(2024, 1, 1), stop=D(2024, 1, 4), span_size=4)

    def test_missing_days_are_filled_with_zeros(self):
        stat = {D(2024, 1, 2): 5, D(2024, 1, 4): 7}

        result = trends._get_span_statistics(stat=stat, span=self.SPAN, span_size=4)

        assert result == build_statistics([0, 5, 0, 7])
        assert result.zero_days == 2

    def test_empty_stat_gives_all_zero_days(self):
        result = trends._get_span_statistics(stat={}, span=self.SPAN, span_size=4)

        assert result == build_statistics([0, 0, 0, 0])

    def test_days_outside_the_span_are_ignored(self):
        stat = {D(2023, 12, 31): 9, D(2024, 1, 1): 1, D(2024, 1, 5): 9}

        result = trends._get_span_statistics(stat=stat, span=self.SPAN, span_size=4)

        assert result == build_statistics([1, 0, 0, 0])

    def test_one_day_span(self):
        span = trends.TimeSpan(start=D(2024, 1, 1), stop=D(2024, 1, 1), span_size=1)

        result = trends._get_span_statistics(stat={D(2024, 1, 1): 3}, span=span, span_size=1)

        assert result == build_statistics([3])
        assert (result.start, result.stop) == (D(2024, 1, 1), D(2024, 1, 1))


class TestGetColors:
    DAYS = ["2024-01-01", "2024-01-02", "2024-01-03"]

    @pytest.mark.parametrize("completion_dates", [None, {}])
    def test_no_completion_dates_give_no_colors(self, completion_dates):
        assert trends._get_colors(completion_dates, self.DAYS) is None

    def test_completion_days_are_green(self):
        completion_dates = {
            "a": datetime.datetime(2024, 1, 2, 23, 59),  # noqa: DTZ001
            "b": datetime.datetime(2024, 1, 2, 0, 0),  # noqa: DTZ001
            "c": datetime.datetime(2025, 1, 1),  # noqa: DTZ001
        }

        colors = trends._get_colors(completion_dates, self.DAYS)

        assert colors == ["steelblue", "green", "steelblue"]

    def test_completion_outside_the_days_colors_nothing_green(self):
        completion_dates = {"a": datetime.datetime(2023, 1, 1)}  # noqa: DTZ001

        assert trends._get_colors(completion_dates, self.DAYS) == ["steelblue"] * 3

    def test_no_days_give_empty_colors(self):
        completion_dates = {"a": datetime.datetime(2024, 1, 1)}  # noqa: DTZ001

        assert trends._get_colors(completion_dates, []) == []
