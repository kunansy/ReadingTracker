from decimal import Decimal

import pytest

from tests.integration import helpers, helpers_materials as h
from tracker.common import database
from tracker.materials import db as materials_db
from tracker.models import enums
from tracker.reading_log import db as logs_db, statistics


BOOK = enums.MaterialTypesEnum.book
ARTICLE = enums.MaterialTypesEnum.article
COURSE = enums.MaterialTypesEnum.course


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> h.Clock:
    return h.freeze_clock(monkeypatch)


def book_log_statistics(history: h.ReadingHistory) -> statistics.LogStatistics:
    return statistics.LogStatistics(
        material_id=history.book,
        total=102,
        lost_time=0,
        duration=3,
        min_record=database.MinMax(
            log_id=history.book_last,
            material_id=history.book,
            date=helpers.day(-7),
            count=22,
        ),
        max_record=database.MinMax(
            log_id=history.book_max,
            material_id=history.book,
            date=helpers.day(-9),
            count=50,
        ),
    )


def article_log_statistics(history: h.ReadingHistory) -> statistics.LogStatistics:
    return statistics.LogStatistics(
        material_id=history.article,
        total=15,
        # day(8) and the six days after the last log
        lost_time=7,
        duration=2,
        min_record=database.MinMax(
            log_id=history.article_min,
            material_id=history.article,
            date=helpers.day(-6),
            count=5,
        ),
        max_record=database.MinMax(
            log_id=history.article_max,
            material_id=history.article,
            date=helpers.day(-9),
            count=10,
        ),
    )


async def test_statistics_parts_are_empty_on_an_empty_database():
    assert await statistics.calculate_materials_stat({h.MISSING_ID}) == {}
    assert await statistics._get_read_pages() == {}
    assert await statistics.get_means() == {}
    assert await statistics.contains(material_id=h.MISSING_ID) is False
    assert await statistics._get_min_record() is None
    assert await statistics._get_max_record() is None
    assert await statistics._get_total_materials_completed() == 0
    assert await statistics._get_materials_completed() == {}


async def test_tracker_statistics_on_an_empty_database():
    assert await statistics.get_tracker_statistics() is None


# calculate_materials_stat


async def test_materials_stat_of_every_material(clock):
    history = await h.reading_history(clock)

    stat = await statistics.calculate_materials_stat({history.book, history.article})

    assert stat == {
        history.book: book_log_statistics(history),
        history.article: article_log_statistics(history),
    }
    assert stat[history.book].mean == 34
    # round(15 / 2) with banker's rounding
    assert stat[history.article].mean == 8


async def test_materials_stat_only_of_the_requested_materials(clock):
    history = await h.reading_history(clock)

    stat = await statistics.calculate_materials_stat({history.book, h.MISSING_ID})

    assert stat == {history.book: book_log_statistics(history)}


async def test_materials_stat_is_empty_for_no_materials(clock):
    await h.reading_history(clock)

    assert await statistics.calculate_materials_stat(set()) == {}


async def test_materials_stat_skips_a_material_without_logs(clock):
    await h.reading_history(clock)
    unread = await h.reading(clock, started=helpers.day(-3))

    assert await statistics.calculate_materials_stat({unread}) == {}


async def test_materials_stat_of_a_single_log_today(clock):
    material_id = await h.reading(clock, started=helpers.day(0))
    log_id = await logs_db.insert_log_record(
        material_id=material_id, count=9, date=helpers.day(0)
    )
    record = database.MinMax(
        log_id=log_id, material_id=material_id, date=helpers.TODAY, count=9
    )

    stat = await statistics.calculate_materials_stat({material_id})

    assert stat == {
        material_id: statistics.LogStatistics(
            material_id=material_id,
            total=9,
            lost_time=0,
            duration=1,
            min_record=record,
            max_record=record,
        ),
    }
    assert stat[material_id].mean == 9


# _get_read_pages, get_means


async def test_read_pages_are_summed_by_material_type(clock):
    await h.reading_history(clock)
    await logs_db.insert_log_record(material_id=h.MISSING_ID, count=1000, date=helpers.day(-1))

    assert await statistics._get_read_pages() == {"book": 102, "article": 15}


async def test_means_are_the_average_of_daily_sums_by_type(clock):
    await h.reading_history(clock)

    means = await statistics.get_means()

    # books: (30 + 50 + 22) / 3 days, articles: (10 + 5) / 2 days
    assert means == {BOOK: Decimal("34.00"), ARTICLE: Decimal("7.50")}


async def test_means_sum_several_logs_of_one_type_within_a_day(clock):
    await h.reading_history(clock)
    second_book = await h.reading(clock, started=helpers.day(-10), title="Second book")
    await logs_db.insert_log_record(material_id=second_book, count=10, date=helpers.day(-10))

    means = await statistics.get_means()

    # books: (30 + 10, 50, 22) / 3 days
    assert means == {BOOK: Decimal("37.33"), ARTICLE: Decimal("7.50")}


async def test_means_skip_types_without_logs(clock):
    await h.reading(clock, started=helpers.day(-3), material_type=COURSE)
    book = await h.reading(clock, started=helpers.day(-3))
    await logs_db.insert_log_record(material_id=book, count=3, date=helpers.day(-1))

    assert await statistics.get_means() == {BOOK: Decimal("3.00")}


# contains, min and max records, completed materials


async def test_contains_is_true_only_for_a_material_with_logs(clock):
    history = await h.reading_history(clock)
    unread = await h.reading(clock, started=helpers.day(-3))

    assert await statistics.contains(material_id=history.book) is True
    assert await statistics.contains(material_id=unread) is False
    assert await statistics.contains(material_id=h.MISSING_ID) is False


async def test_min_record_of_the_whole_log_and_of_a_material(clock):
    history = await h.reading_history(clock)

    assert await statistics._get_min_record() == database.MinMax(
        log_id=history.article_min,
        material_id=history.article,
        material_title="Article",
        count=5,
        date=helpers.day(-6),
    )
    assert await statistics._get_min_record(material_id=history.book) == database.MinMax(
        log_id=history.book_last,
        material_id=history.book,
        material_title="Book",
        count=22,
        date=helpers.day(-7),
    )


async def test_max_record_of_the_whole_log_and_of_a_material(clock):
    history = await h.reading_history(clock)

    assert await statistics._get_max_record() == database.MinMax(
        log_id=history.book_max,
        material_id=history.book,
        material_title="Book",
        count=50,
        date=helpers.day(-9),
    )
    assert await statistics._get_max_record(
        material_id=history.article
    ) == database.MinMax(
        log_id=history.article_max,
        material_id=history.article,
        material_title="Article",
        count=10,
        date=helpers.day(-9),
    )


async def test_min_and_max_records_are_none_for_a_material_without_logs(clock):
    await h.reading_history(clock)
    unread = await h.reading(clock, started=helpers.day(-3))

    assert await statistics._get_min_record(material_id=unread) is None
    assert await statistics._get_max_record(material_id=unread) is None


async def test_completed_materials_are_counted_by_type(clock):
    await h.completed(clock, started=helpers.day(-9), finished=helpers.day(-5))
    await h.completed(clock, started=helpers.day(-9), finished=helpers.day(0))
    await h.completed(clock, started=helpers.day(-9), finished=helpers.day(-1), material_type=ARTICLE)
    await h.reading(clock, started=helpers.day(-9), material_type=COURSE)
    await h.queued(clock, material_type=COURSE)

    assert await statistics._get_materials_completed() == {"book": 2, "article": 1}
    assert await statistics._get_total_materials_completed() == 3


async def test_no_materials_are_completed_when_all_are_queued_or_reading(clock):
    await h.reading(clock, started=helpers.day(-9))
    await h.queued(clock)

    assert await statistics._get_materials_completed() == {}
    assert await statistics._get_total_materials_completed() == 0


# get_tracker_statistics


async def test_tracker_statistics_of_a_reading_history(clock):
    history = await h.reading_history(clock)

    result = await statistics.get_tracker_statistics()

    assert result == statistics.TrackerStatistics(
        started_at=helpers.day(-10),
        finished_at=helpers.day(-6),
        duration=5,
        # day(8) is the only day without logs between the first and the last log
        lost_time=1,
        # (34.00 + 7.50) / 2
        mean=20.75,
        # of 30, 50, 10, 22, 5
        median=22,
        pages_read={BOOK: 102, ARTICLE: 15},
        materials_completed={BOOK: 1},
        total_materials_completed=1,
        # 117 pages read plus round(20.75) for the lost day
        would_be_total=138,
        min_log_record=database.MinMax(
            log_id=history.article_min,
            material_id=history.article,
            material_title="Article",
            count=5,
            date=helpers.day(-6),
        ),
        max_log_record=database.MinMax(
            log_id=history.book_max,
            material_id=history.book,
            material_title="Book",
            count=50,
            date=helpers.day(-9),
        ),
    )
    assert result.duration_period == "5 days"
    assert result.lost_time_period == "1 days"
    assert result.total_pages_read == 117
    assert result.lost_time_percent == 20.0
    # round(138 / 117, 2) * 100
    assert result.would_be_total_percent == pytest.approx(118.0)


async def test_tracker_statistics_of_a_single_log(clock):
    material_id = await h.reading(clock, started=helpers.day(-1), title="Only")
    log_id = await logs_db.insert_log_record(
        material_id=material_id, count=7, date=helpers.day(-1)
    )
    record = database.MinMax(
        log_id=log_id,
        material_id=material_id,
        material_title="Only",
        count=7,
        date=helpers.day(-1),
    )

    result = await statistics.get_tracker_statistics()

    assert result == statistics.TrackerStatistics(
        started_at=helpers.day(-1),
        finished_at=helpers.day(-1),
        duration=1,
        lost_time=0,
        mean=7.0,
        median=7,
        pages_read={BOOK: 7},
        materials_completed={},
        total_materials_completed=0,
        would_be_total=7,
        min_log_record=record,
        max_log_record=record,
    )
    assert result.duration_period == "1 days"
    assert result.lost_time_period == ""
    assert result.lost_time_percent == 0.0
    assert result.would_be_total_percent == 100.0


async def test_tracker_mean_ignores_courses(clock):
    book = await h.reading(clock, started=helpers.day(-1))
    course = await h.reading(clock, started=helpers.day(-1), material_type=COURSE)
    await logs_db.insert_log_record(material_id=book, count=10, date=helpers.day(-1))
    await logs_db.insert_log_record(material_id=course, count=100, date=helpers.day(-1))

    result = await statistics.get_tracker_statistics()

    assert result.mean == 10.0
    assert result.median == 55.0
    assert result.pages_read == {BOOK: 10, COURSE: 100}
    assert (result.duration, result.lost_time, result.would_be_total) == (1, 0, 110)


async def test_tracker_mean_is_zero_when_only_courses_are_logged(clock):
    course = await h.reading(clock, started=helpers.day(-1), material_type=COURSE)
    await logs_db.insert_log_record(material_id=course, count=100, date=helpers.day(-1))

    result = await statistics.get_tracker_statistics()

    assert result.mean == 0.0
    assert result.pages_read == {COURSE: 100}


async def test_tracker_statistics_count_materials_completed_without_logs(clock):
    await h.completed(clock, started=helpers.day(-9), finished=helpers.day(-5), material_type=ARTICLE)
    book = await h.reading(clock, started=helpers.day(-1))
    await logs_db.insert_log_record(material_id=book, count=10, date=helpers.day(-1))

    result = await statistics.get_tracker_statistics()

    assert result.materials_completed == {ARTICLE: 1}
    assert result.total_materials_completed == 1


async def test_tracker_statistics_percent_fails_on_zero_pages_read_current_behaviour(
    clock,
):
    material_id = await h.reading(clock, started=helpers.day(-1))
    await logs_db.insert_log_record(material_id=material_id, count=0, date=helpers.day(-1))

    result = await statistics.get_tracker_statistics()

    assert result.total_pages_read == 0
    # reading_log/statistics.py:66 divides by the total of 0
    with pytest.raises(ZeroDivisionError):
        result.model_dump()


async def test_tracker_statistics_fail_on_logs_of_unknown_materials_current_behaviour():
    await logs_db.insert_log_record(material_id=h.MISSING_ID, count=5, date=helpers.day(-1))

    # reading_log/statistics.py:235 no material joins the log, so there are no means
    with pytest.raises(ZeroDivisionError):
        await statistics.get_tracker_statistics()


async def test_material_statistics_use_the_log_statistics_of_the_material(clock):
    history = await h.reading_history(clock)

    [article] = await materials_db.reading_statistics()
    log_statistics = article_log_statistics(history)

    assert (article.total, article.duration, article.lost_time, article.mean) == (
        log_statistics.total,
        log_statistics.duration,
        log_statistics.lost_time,
        log_statistics.mean,
    )
    assert article.min_record == log_statistics.min_record
    assert article.max_record == log_statistics.max_record
