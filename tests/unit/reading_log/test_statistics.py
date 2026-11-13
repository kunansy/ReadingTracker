import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest

from tests.unit.helpers import day, midnight, uid
from tracker.common import database
from tracker.models import enums
from tracker.reading_log import db, statistics as st


A, B = uid(0xA), uid(0xB)
BOOK = enums.MaterialTypesEnum.book
ARTICLE = enums.MaterialTypesEnum.article
COURSE = enums.MaterialTypesEnum.course


def _log(material_id: UUID, offset: int, count: int = 10, *, log_id: int = 0) -> db.LogRecord:
    return db.LogRecord(
        log_id=UUID(int=log_id or 1000 + offset),
        material_id=material_id,
        count=count,
        date=day(offset),
    )


def _filler(material_id: UUID, offset: int) -> db.LogRecord:
    return db.LogRecord(material_id=material_id, count=0, date=day(offset))


def _tracker_statistics(**overrides) -> st.TrackerStatistics:
    fields = {
        "started_at": day(-9),
        "finished_at": day(0),
        "duration": 10,
        "lost_time": 4,
        "mean": 12.5,
        "median": 10.0,
        "pages_read": {BOOK: 60, ARTICLE: 11},
        "materials_completed": {BOOK: 1},
        "total_materials_completed": 1,
        "would_be_total": 142,
        "min_log_record": None,
        "max_log_record": None,
    }
    return st.TrackerStatistics(**(fields | overrides))


@pytest.mark.parametrize(
    ("total", "duration", "expected"),
    [
        (0, 0, 0),
        (10, 0, 10),
        (0, 5, 0),
        (10, 3, 3),
        (11, 3, 4),
        (5, 2, 2),
        (7, 2, 4),
        (100, 1, 100),
    ],
    ids=[
        "nothing-read",
        "zero-duration-is-one-day",
        "zero-total",
        "rounds-down",
        "rounds-up",
        "half-to-even-down",
        "half-to-even-up",
        "single-day",
    ],
)
def test_log_statistics_mean(total, duration, expected):
    stat = st.LogStatistics(material_id=A, total=total, lost_time=0, duration=duration)

    assert stat.mean == expected
    assert stat.model_dump()["mean"] == expected


def test_tracker_statistics_periods_and_total():
    stat = _tracker_statistics(duration=706, lost_time=31)

    assert stat.duration_period == "1 years, 11 months, 11 days"
    assert stat.lost_time_period == "1 months, 1 days"
    assert stat.total_pages_read == 71


def test_tracker_statistics_without_lost_time_has_empty_period():
    stat = _tracker_statistics(lost_time=0)

    assert stat.lost_time_period == ""
    assert stat.lost_time_percent == 0.0


@pytest.mark.parametrize(
    ("lost_time", "duration", "expected"),
    [(23, 100, 23.0), (1, 3, 33.33), (2, 3, 66.67), (10, 10, 100.0)],
    ids=["exact", "rounds-down", "rounds-up", "everything-lost"],
)
def test_lost_time_percent(lost_time, duration, expected):
    stat = _tracker_statistics(lost_time=lost_time, duration=duration)

    assert stat.lost_time_percent == expected


def test_total_pages_read_of_nothing_is_zero():
    assert _tracker_statistics(pages_read={}).total_pages_read == 0


@pytest.mark.parametrize(
    ("would_be_total", "pages_read", "expected"),
    [(142, 71, 200.0), (71, 71, 100.0), (100, 80, 125.0)],
    ids=["twice", "nothing-lost", "quarter-more"],
)
def test_would_be_total_percent_is_the_ratio_to_pages_read(would_be_total, pages_read, expected):
    stat = _tracker_statistics(would_be_total=would_be_total, pages_read={BOOK: pages_read})

    assert stat.would_be_total_percent == expected


def test_would_be_total_percent_is_scaled_after_rounding_current_behaviour():
    """round(1.15, 2) * 100 is a binary float artefact, not 115.0."""
    stat = _tracker_statistics(would_be_total=115, pages_read={BOOK: 100})

    assert stat.would_be_total_percent == 114.99999999999999
    assert stat.would_be_total_percent != 115.0


@pytest.mark.parametrize("pages_read", [{}, {BOOK: 0}], ids=["no-types", "zero-pages"])
def test_would_be_total_percent_without_pages_read_divides_by_zero_current_behaviour(
    pages_read,
):
    stat = _tracker_statistics(would_be_total=0, pages_read=pages_read)

    with pytest.raises(ZeroDivisionError):
        _ = stat.would_be_total_percent
    with pytest.raises(ZeroDivisionError):
        stat.model_dump()


def test_lost_time_percent_of_zero_duration_divides_by_zero_current_behaviour():
    stat = _tracker_statistics(duration=0, lost_time=0)

    with pytest.raises(ZeroDivisionError):
        _ = stat.lost_time_percent


def test_started_and_finished_dates_are_the_extreme_log_dates():
    logs = [_log(A, -3), _log(B, -7), _log(A, 0), _log(B, -1)]

    assert st._calc_started_at(logs) == day(-7)
    assert st._calc_finished_at(logs) == day(0)


def test_started_and_finished_dates_of_a_single_log_coincide():
    logs = [_log(A, -3)]

    assert st._calc_started_at(logs) == st._calc_finished_at(logs) == day(-3)


def test_started_at_of_empty_log_raises():
    with pytest.raises(ValueError, match="^Could not find start date, no records found$"):
        st._calc_started_at([])


def test_finished_at_of_empty_log_raises():
    with pytest.raises(ValueError, match="^Could not find last date, no records found$"):
        st._calc_finished_at([])


@pytest.mark.parametrize(
    ("started_at", "finished_at", "expected"),
    [
        (datetime.date(2024, 3, 10), datetime.date(2024, 3, 10), 1),
        (datetime.date(2024, 3, 9), datetime.date(2024, 3, 10), 2),
        (datetime.date(2024, 2, 28), datetime.date(2024, 3, 1), 3),
        (datetime.date(2023, 2, 28), datetime.date(2023, 3, 1), 2),
        (datetime.date(2023, 1, 1), datetime.date(2023, 12, 31), 365),
    ],
    ids=["one-day", "two-days", "leap-february", "common-february", "whole-year"],
)
def test_log_duration_includes_both_ends(started_at, finished_at, expected):
    assert st._calc_log_duration(started_at, finished_at) == expected


@pytest.mark.parametrize(
    ("duration", "logs", "expected"),
    [
        (1, [_log(A, 0)], 0),
        (5, [_log(A, -4), _log(A, 0)], 3),
        (3, [_log(A, -2), _log(B, -2), _log(A, 0)], 1),
        (3, [_log(A, -2), _log(A, -1), _log(A, 0)], 0),
        (4, [], 4),
    ],
    ids=["single-day", "gap", "two-materials-on-one-day-count-once", "no-gaps", "no-logs"],
)
def test_lost_days_are_days_without_any_log(duration, logs, expected):
    assert st._calc_lost_days(duration, logs) == expected


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ([7], 7),
        ([1, 3], 2.0),
        ([1, 2], 1.5),
        ([5, 1, 3], 3),
        ([10, 10, 10, 1], 10.0),
        ([0, 0, 9], 0),
    ],
    ids=["single", "even", "even-fractional", "odd-unsorted", "duplicates", "zeroes"],
)
def test_median_pages_read_per_day(counts, expected):
    logs = [_log(A, -index, count) for index, count in enumerate(counts)]

    assert st._calc_median_pages_read_per_day(logs) == expected


def test_median_of_empty_log_raises():
    import statistics

    with pytest.raises(statistics.StatisticsError):
        st._calc_median_pages_read_per_day([])


@pytest.mark.parametrize(
    ("means", "total_read_pages", "lost_time", "expected"),
    [
        ({BOOK: Decimal(20)}, 100, 3, 160),
        ({BOOK: Decimal(20), ARTICLE: Decimal(5)}, 100, 2, 124),
        ({BOOK: Decimal("0.4")}, 100, 5, 100),
        ({BOOK: Decimal(20)}, 100, 0, 100),
        ({BOOK: Decimal(20)}, 0, 2, 40),
        ({BOOK: Decimal(30), COURSE: Decimal(2)}, 10, 1, 26),
    ],
    ids=[
        "single-type",
        "average-of-types-half-to-even",
        "mean-rounds-to-zero",
        "nothing-lost",
        "nothing-read",
        "course-is-included",
    ],
)
def test_would_be_total_adds_mean_pages_for_every_lost_day(
    means,
    total_read_pages,
    lost_time,
    expected,
):
    result = st._would_be_total(
        means=means,
        total_read_pages=total_read_pages,
        lost_time=lost_time,
    )

    assert result == expected


def test_would_be_total_without_means_divides_by_zero_current_behaviour():
    with pytest.raises(ZeroDivisionError):
        st._would_be_total(means={}, total_read_pages=10, lost_time=1)


@pytest.mark.parametrize(
    ("means", "expected"),
    [
        ({}, 0.0),
        ({COURSE: Decimal(50)}, 0.0),
        ({BOOK: Decimal(20)}, 20.0),
        ({BOOK: Decimal(20), ARTICLE: Decimal(5)}, 12.5),
        ({BOOK: Decimal(20), ARTICLE: Decimal(5), COURSE: Decimal(500)}, 12.5),
        ({BOOK: Decimal("10.01"), ARTICLE: Decimal("10.02"), enums.MaterialTypesEnum.lecture: Decimal(10)}, 10.01),
    ],
    ids=["empty", "only-course", "single", "two-types", "course-is-ignored", "rounded"],
)
def test_tracker_mean_averages_types_except_courses(means, expected):
    source = dict(means)

    assert st._tracker_mean(means) == expected
    assert means == source


def _data_of(*records: db.LogRecord):
    async def _data():
        for record in records:
            yield record.date, record

    return _data


async def test_materials_stat_counts_reading_and_lost_days(mocker):
    mocker.patch.object(
        db,
        "data",
        _data_of(
            _log(A, -4, 10, log_id=1),
            _filler(A, -3),
            _log(A, -2, 5, log_id=2),
            _log(A, -1, 20, log_id=3),
            _filler(A, 0),
        ),
    )

    stat = await st.calculate_materials_stat({A})

    assert stat == {
        A: st.LogStatistics(
            material_id=A,
            total=35,
            lost_time=2,
            duration=3,
            min_record=database.MinMax(log_id=UUID(int=2), material_id=A, date=day(-2), count=5),
            max_record=database.MinMax(log_id=UUID(int=3), material_id=A, date=day(-1), count=20),
        ),
    }
    assert stat[A].mean == 12


async def test_materials_stat_keeps_the_first_of_equal_min_and_max_records(mocker):
    mocker.patch.object(
        db,
        "data",
        _data_of(_log(A, -2, 7, log_id=1), _log(A, -1, 7, log_id=2), _log(A, 0, 7, log_id=3)),
    )

    stat = await st.calculate_materials_stat({A})

    assert stat[A].min_record.log_id == UUID(int=1)
    assert stat[A].max_record.log_id == UUID(int=1)
    assert stat[A].min_record.date == stat[A].max_record.date == day(-2)


async def test_materials_stat_of_a_single_record(mocker):
    mocker.patch.object(db, "data", _data_of(_log(A, 0, 3, log_id=1)))

    stat = await st.calculate_materials_stat({A})

    assert (stat[A].total, stat[A].duration, stat[A].lost_time, stat[A].mean) == (3, 1, 0, 3)
    assert stat[A].min_record == stat[A].max_record
    assert stat[A].min_record.material_title == ""


async def test_materials_stat_separates_materials_and_skips_unrequested_ones(mocker):
    mocker.patch.object(
        db,
        "data",
        _data_of(
            _log(A, -3, 10),
            _log(B, -2, 4),
            _filler(B, -1),
            _log(uid(0xC), -1, 99),
            _log(A, 0, 30),
        ),
    )

    stat = await st.calculate_materials_stat({A, B, uid(0xD)})

    assert stat.keys() == {A, B}
    assert (stat[A].total, stat[A].duration, stat[A].lost_time) == (40, 2, 0)
    assert (stat[B].total, stat[B].duration, stat[B].lost_time) == (4, 1, 1)
    assert (stat[A].min_record.count, stat[A].max_record.count) == (10, 30)
    assert (stat[B].min_record.count, stat[B].max_record.count) == (4, 4)


@pytest.mark.parametrize("material_ids", [set(), {uid(0xD)}], ids=["no-ids", "unknown-id"])
async def test_materials_stat_of_unknown_materials_is_empty(mocker, material_ids):
    mocker.patch.object(db, "data", _data_of(_log(A, 0)))

    assert await st.calculate_materials_stat(material_ids) == {}


async def test_materials_stat_of_empty_log_is_empty(mocker):
    mocker.patch.object(db, "data", _data_of())

    assert await st.calculate_materials_stat({A}) == {}


async def test_zero_count_record_stays_the_minimum_current_behaviour(mocker):
    mocker.patch.object(
        db,
        "data",
        _data_of(_log(A, -1, 0, log_id=1), _log(A, 0, 5, log_id=2)),
    )

    stat = await st.calculate_materials_stat({A})

    assert stat[A].min_record.count == 0
    assert stat[A].max_record.count == 5
    assert (stat[A].duration, stat[A].lost_time) == (1, 1)


async def test_filler_days_of_the_real_log_never_reach_min_max_records(mocker, frozen_now):
    """A material enters `db.data()` through a real record, so a filler day (log_id=None)
    can never be the first record of a material and never builds a MinMax.
    """
    mocker.patch.object(
        db,
        "list_log_records",
        mocker.AsyncMock(
            return_value=[
                _log(A, -6, 10, log_id=1),
                _log(B, -4, 4, log_id=2),
                _log(A, -1, 2, log_id=3),
            ],
        ),
    )
    mocker.patch.object(
        db,
        "get_completion_dates",
        mocker.AsyncMock(return_value={B: midnight(-3)}),
    )

    stat = await st.calculate_materials_stat({A, B})

    assert (stat[A].total, stat[A].duration, stat[A].lost_time) == (12, 2, 3)
    assert (stat[B].total, stat[B].duration, stat[B].lost_time) == (4, 1, 1)
    assert stat[A].min_record.log_id == UUID(int=3)
    assert stat[A].max_record.log_id == UUID(int=1)
    assert stat[B].min_record.log_id == stat[B].max_record.log_id == UUID(int=2)


@pytest.fixture
def tracker_sources(mocker):
    min_record = database.MinMax(log_id=uid(1), material_id=A, material_title="a", count=1, date=day(-9))
    max_record = database.MinMax(log_id=uid(2), material_id=B, material_title="b", count=50, date=day(0))
    return SimpleNamespace(
        min_record=min_record,
        max_record=max_record,
        list_log_records=mocker.patch.object(
            db,
            "list_log_records",
            mocker.AsyncMock(
                return_value=[
                    _log(B, 0, 50),
                    _log(A, -5, 10),
                    _log(B, -5, 20),
                    _log(A, -9, 1),
                ],
            ),
        ),
        get_means=mocker.patch.object(
            st,
            "get_means",
            mocker.AsyncMock(return_value={BOOK: Decimal("15.5"), ARTICLE: Decimal(5)}),
        ),
        get_read_pages=mocker.patch.object(
            st,
            "_get_read_pages",
            mocker.AsyncMock(return_value={BOOK: 61, ARTICLE: 20}),
        ),
        get_min_record=mocker.patch.object(
            st,
            "_get_min_record",
            mocker.AsyncMock(return_value=min_record),
        ),
        get_max_record=mocker.patch.object(
            st,
            "_get_max_record",
            mocker.AsyncMock(return_value=max_record),
        ),
        get_materials_completed=mocker.patch.object(
            st,
            "_get_materials_completed",
            mocker.AsyncMock(return_value={BOOK: 2, ARTICLE: 3}),
        ),
    )


async def test_tracker_statistics_are_assembled_from_the_log(tracker_sources):
    stat = await st.get_tracker_statistics()

    assert stat == st.TrackerStatistics(
        started_at=day(-9),
        finished_at=day(0),
        duration=10,
        lost_time=7,
        mean=10.25,
        median=15.0,
        pages_read={BOOK: 61, ARTICLE: 20},
        materials_completed={BOOK: 2, ARTICLE: 3},
        total_materials_completed=5,
        # round((15.5 + 5) / 2) == 10 pages for each of the 7 lost days
        would_be_total=81 + 10 * 7,
        min_log_record=tracker_sources.min_record,
        max_log_record=tracker_sources.max_record,
    )
    assert stat.total_pages_read == 81
    assert stat.lost_time_percent == 70.0
    assert stat.duration_period == "10 days"
    tracker_sources.list_log_records.assert_awaited_once_with()
    tracker_sources.get_min_record.assert_awaited_once_with()
    tracker_sources.get_max_record.assert_awaited_once_with()


async def test_tracker_statistics_of_a_single_log_day(tracker_sources):
    tracker_sources.list_log_records.return_value = [_log(A, 0, 8)]
    tracker_sources.get_read_pages.return_value = {BOOK: 8}
    tracker_sources.get_materials_completed.return_value = {}
    tracker_sources.get_min_record.return_value = None
    tracker_sources.get_max_record.return_value = None

    stat = await st.get_tracker_statistics()

    assert (stat.started_at, stat.finished_at, stat.duration) == (day(0), day(0), 1)
    assert (stat.lost_time, stat.median, stat.would_be_total) == (0, 8, 8)
    assert stat.total_materials_completed == 0
    assert stat.materials_completed == {}
    assert stat.min_log_record is None
    assert stat.max_log_record is None
    assert stat.would_be_total_percent == 100.0


async def test_tracker_statistics_of_empty_log_are_none(tracker_sources):
    tracker_sources.list_log_records.return_value = []

    assert await st.get_tracker_statistics() is None
    tracker_sources.get_means.assert_not_awaited()
    tracker_sources.get_read_pages.assert_not_awaited()


async def test_tracker_statistics_without_means_divide_by_zero_current_behaviour(
    tracker_sources,
):
    """Reachable only when every log record points to a material that no longer exists."""
    tracker_sources.get_means.return_value = {}

    with pytest.raises(ZeroDivisionError):
        await st.get_tracker_statistics()
