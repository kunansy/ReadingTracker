import datetime
from uuid import UUID

import pytest

from tests.integration import factories, helpers, helpers_materials as h
from tracker.common import database, sort_keys
from tracker.common.pagination import PageParams
from tracker.materials import db as materials_db
from tracker.models import models
from tracker.reading_log import db


FIXED_ID = "018e4a6c-0000-7000-8000-00000000abcd"


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> h.Clock:
    return h.freeze_clock(monkeypatch)


async def collect_data(**kwargs) -> list[tuple[datetime.date, UUID, int, UUID | None]]:
    """Rows of `data()`; the order of logs sharing a day is not defined, so it is normalised."""
    rows = [
        (date, record.material_id, record.count, record.log_id)
        async for date, record in db.data(**kwargs)
    ]
    assert [row[0] for row in rows] == sorted(row[0] for row in rows)
    return sorted(rows, key=lambda row: (row[0], row[2]))


# insert_log_record


async def test_insert_log_record_stores_every_column(clock, mocker):
    material_id = await h.reading(clock, started=helpers.day(-5))
    mocker.patch.object(models, "generate_id", return_value=FIXED_ID)

    log_id = await db.insert_log_record(material_id=material_id, count=17, date=helpers.day(-1))

    assert log_id == UUID(FIXED_ID)
    assert await factories.fetch_row(models.ReadingLog, log_id) == {
        "log_id": UUID(FIXED_ID),
        "material_id": material_id,
        "count": 17,
        "date": datetime.date(2024, 3, 14),
        "sort_key": f"{material_id}$$2024-03-14$${FIXED_ID}",
    }


async def test_insert_log_record_sort_key_matches_the_generator(clock):
    material_id = await h.reading(clock, started=helpers.day(-5))

    log_id = await db.insert_log_record(
        material_id=str(material_id), count=1, date=helpers.day(-2)
    )

    row = await factories.fetch_row(models.ReadingLog, log_id)
    assert row["material_id"] == material_id
    assert row["sort_key"] == sort_keys.reading_log_sort_key(
        material_id=material_id,
        date=helpers.day(-2),
        log_id=log_id,
    )


async def test_insert_log_record_rejects_a_second_log_of_the_material_on_the_same_day(
    clock,
):
    material_id = await h.reading(clock, started=helpers.day(-5))
    log_id = await db.insert_log_record(material_id=material_id, count=1, date=helpers.day(-1))

    with pytest.raises(database.AlreadyExistsException):
        await db.insert_log_record(material_id=material_id, count=2, date=helpers.day(-1))

    assert await db.list_log_records() == [
        db.LogRecord(log_id=log_id, date=helpers.day(-1), count=1, material_id=material_id),
    ]


async def test_insert_log_record_allows_same_day_for_another_material_and_another_day(
    clock,
):
    material_id = await h.reading(clock, started=helpers.day(-5))
    other_id = await h.reading(clock, started=helpers.day(-5))

    await db.insert_log_record(material_id=material_id, count=1, date=helpers.day(-1))
    await db.insert_log_record(material_id=other_id, count=1, date=helpers.day(-1))
    await db.insert_log_record(material_id=material_id, count=1, date=helpers.day(-2))

    assert await factories.count_rows(models.ReadingLog) == 3


@pytest.mark.parametrize("count", [0, -5], ids=["zero", "negative"])
async def test_insert_log_record_does_not_validate_the_count_current_behaviour(
    clock, count
):
    material_id = await h.reading(clock, started=helpers.day(-5))

    log_id = await db.insert_log_record(
        material_id=material_id, count=count, date=helpers.day(-1)
    )

    assert (await db.get_log_record(log_id=log_id)).count == count


async def test_insert_log_record_accepts_an_unknown_material_current_behaviour():
    log_id = await db.insert_log_record(material_id=h.MISSING_ID, count=1, date=helpers.day(-1))

    assert (await db.get_log_record(log_id=log_id)).material_id == h.MISSING_ID


async def test_insert_log_record_rejects_a_count_past_the_integer_range(clock):
    material_id = await h.reading(clock, started=helpers.day(-5))

    with pytest.raises(database.DatabaseException):
        await db.insert_log_record(material_id=material_id, count=2**31, date=helpers.day(-1))

    assert await db.is_log_empty() is True


async def test_reading_log_date_column_default_stores_a_date(clock):
    """models.py:108 defaults a Date column to a datetime; asyncpg truncates it to the date."""
    stmt = models.ReadingLog.insert().values(
        log_id=FIXED_ID,
        material_id=h.MISSING_ID,
        count=1,
        sort_key="default-date",
    )
    before = models._utc_now().date()

    async with database.session() as ses:
        await ses.execute(stmt)

    row = await factories.fetch_row(models.ReadingLog, UUID(FIXED_ID))
    assert type(row["date"]) is datetime.date
    assert before <= row["date"] <= models._utc_now().date()


# list_log_records, get_log_record


@pytest.fixture
async def logs(clock: h.Clock) -> dict[str, UUID]:
    first = await h.reading(clock, started=helpers.day(-9))
    second = await h.reading(clock, started=helpers.day(-9))
    return {
        "first": first,
        "second": second,
        "first day5": await db.insert_log_record(
            material_id=first, count=5, date=helpers.day(-5)
        ),
        "first day3": await db.insert_log_record(
            material_id=first, count=3, date=helpers.day(-3)
        ),
        "second day3": await db.insert_log_record(
            material_id=second, count=30, date=helpers.day(-3)
        ),
        "first day1": await db.insert_log_record(
            material_id=first, count=1, date=helpers.day(-1)
        ),
    }


async def test_list_log_records_is_empty_without_logs():
    assert await db.list_log_records() == []
    assert await db.list_log_records(material_id=h.MISSING_ID) == []


async def test_list_log_records_returns_records_from_the_latest_date(clock):
    material_id = await h.reading(clock, started=helpers.day(-9))
    old = await db.insert_log_record(material_id=material_id, count=5, date=helpers.day(-5))
    new = await db.insert_log_record(material_id=material_id, count=1, date=helpers.day(-1))
    middle = await db.insert_log_record(material_id=material_id, count=3, date=helpers.day(-3))

    assert await db.list_log_records() == [
        db.LogRecord(log_id=new, date=helpers.day(-1), count=1, material_id=material_id),
        db.LogRecord(log_id=middle, date=helpers.day(-3), count=3, material_id=material_id),
        db.LogRecord(log_id=old, date=helpers.day(-5), count=5, material_id=material_id),
    ]


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({}, ["first day1", "first day3", "second day3", "first day5"]),
        ({"material_id": "first"}, ["first day1", "first day3", "first day5"]),
        ({"material_id": "second"}, ["second day3"]),
        ({"from_date": helpers.day(-3)}, ["first day1", "first day3", "second day3"]),
        ({"from_date": helpers.day(-2)}, ["first day1"]),
        ({"from_date": helpers.day(0)}, []),
        ({"to_date": helpers.day(-3)}, ["first day3", "second day3", "first day5"]),
        ({"to_date": helpers.day(-4)}, ["first day5"]),
        ({"to_date": helpers.day(-6)}, []),
        ({"from_date": helpers.day(-3), "to_date": helpers.day(-3)}, ["first day3", "second day3"]),
        (
            {"from_date": helpers.day(-5), "to_date": helpers.day(-1)},
            ["first day1", "first day3", "second day3", "first day5"],
        ),
        ({"from_date": helpers.day(-1), "to_date": helpers.day(-5)}, []),
        (
            {"material_id": "first", "from_date": helpers.day(-4), "to_date": helpers.day(-2)},
            ["first day3"],
        ),
        ({"material_id": "second", "from_date": helpers.day(-2)}, []),
    ],
    ids=[
        "no filters",
        "first material",
        "second material",
        "from a date with logs, inclusive",
        "from the day after",
        "from today",
        "to a date with logs, inclusive",
        "to the day before",
        "to a date before every log",
        "one-day range",
        "whole range",
        "reversed range",
        "material and range",
        "material without logs in the range",
    ],
)
async def test_list_log_records_filters(logs, filters, expected):
    if "material_id" in filters:
        filters = filters | {"material_id": logs[filters["material_id"]]}

    records = await db.list_log_records(**filters)

    assert sorted(record.log_id for record in records) == sorted(
        logs[n] for n in expected
    )
    dates = [record.date for record in records]
    assert dates == sorted(dates, reverse=True)


async def test_list_log_records_page_returns_the_same_records(logs):
    records = await db.list_log_records(material_id=logs["first"])

    page = await db.list_log_records_page(material_id=logs["first"], params=PageParams())

    assert page.items == records
    assert page.total_count == 3
    assert page.next_token is None


async def test_get_log_record_returns_the_record(logs):
    record = await db.get_log_record(log_id=logs["second day3"])

    assert record == db.LogRecord(
        log_id=logs["second day3"],
        date=helpers.day(-3),
        count=30,
        material_id=logs["second"],
        material_title=None,
    )


async def test_get_log_record_raises_not_found_for_a_missing_id(logs):
    with pytest.raises(database.NotFoundException, match=str(h.MISSING_ID)):
        await db.get_log_record(log_id=h.MISSING_ID)


# get_completion_dates, is_log_empty, records_sum


async def test_completion_dates_are_empty_without_completed_materials(clock):
    await h.queued(clock)
    await h.reading(clock, started=helpers.day(-3))

    assert await db.get_completion_dates() == {}


async def test_completion_dates_include_only_completed_materials(clock):
    await h.reading(clock, started=helpers.day(-3))
    first = await h.completed(clock, started=helpers.day(-9), finished=helpers.day(-4))
    second = await h.completed(clock, started=helpers.day(-9), finished=helpers.day(0))

    assert await db.get_completion_dates() == {
        first: helpers.at(helpers.day(-4)),
        second: helpers.at(helpers.day(0)),
    }


async def test_log_is_empty_without_records(clock):
    await h.reading(clock, started=helpers.day(-3))

    assert await db.is_log_empty() is True


async def test_log_is_not_empty_with_a_record(logs):
    assert await db.is_log_empty() is False


async def test_records_sum_is_zero_without_logs():
    assert await db.records_sum() == 0
    assert await db.records_sum(from_date=helpers.day(-5), to_date=helpers.day(-1)) == 0


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({}, 39),
        ({"from_date": helpers.day(-3)}, 34),
        ({"from_date": helpers.day(-2)}, 1),
        ({"to_date": helpers.day(-3)}, 38),
        ({"to_date": helpers.day(-4)}, 5),
        ({"from_date": helpers.day(-3), "to_date": helpers.day(-3)}, 33),
        ({"from_date": helpers.day(-4), "to_date": helpers.day(-4)}, 0),
        ({"from_date": helpers.day(-1), "to_date": helpers.day(-5)}, 0),
        ({"from_date": helpers.day(0)}, 0),
    ],
    ids=[
        "no filters",
        "from a date with logs, inclusive",
        "from the day after",
        "to a date with logs, inclusive",
        "to the day before",
        "one-day range",
        "one-day range without logs",
        "reversed range",
        "from today",
    ],
)
async def test_records_sum_filters(logs, filters, expected):
    assert await db.records_sum(**filters) == expected


async def test_data_yields_nothing_without_logs(clock):
    await h.reading(clock, started=helpers.day(-3))

    assert await collect_data() == []


async def test_data_fills_every_day_from_the_first_log_until_today(clock):
    history = await h.reading_history(clock)
    book, article = history.book, history.article

    rows = await collect_data()

    assert rows == [
        (helpers.day(-10), book, 30, history.book_first),
        (helpers.day(-9), article, 10, history.article_max),
        (helpers.day(-9), book, 50, history.book_max),
        (helpers.day(-8), article, 0, None),
        (helpers.day(-7), book, 22, history.book_last),
        (helpers.day(-6), article, 5, history.article_min),
        *[(helpers.day(-days), article, 0, None) for days in (5, 4, 3, 2, 1, 0)],
    ]


async def test_data_ends_at_the_frozen_today(clock):
    material_id = await h.reading(clock, started=helpers.day(-3))
    log_id = await db.insert_log_record(material_id=material_id, count=4, date=helpers.day(0))

    assert await collect_data() == [(helpers.TODAY, material_id, 4, log_id)]


async def test_data_gives_an_empty_day_to_the_material_read_last(clock):
    first = await h.reading(clock, started=helpers.day(-9))
    second = await h.reading(clock, started=helpers.day(-9))
    first_old = await db.insert_log_record(material_id=first, count=1, date=helpers.day(-3))
    second_log = await db.insert_log_record(material_id=second, count=2, date=helpers.day(-2))
    first_new = await db.insert_log_record(material_id=first, count=3, date=helpers.day(-1))

    rows = await collect_data()

    assert rows == [
        (helpers.day(-3), first, 1, first_old),
        (helpers.day(-2), second, 2, second_log),
        (helpers.day(-1), first, 3, first_new),
        (helpers.day(0), first, 0, None),
    ]


async def test_data_returns_to_the_previous_material_after_a_completion(clock):
    long_read = await h.reading(clock, started=helpers.day(-9))
    short_read = await h.reading(clock, started=helpers.day(-9))
    long_log = await db.insert_log_record(material_id=long_read, count=1, date=helpers.day(-4))
    short_log = await db.insert_log_record(material_id=short_read, count=2, date=helpers.day(-3))
    await materials_db.complete_material(material_id=short_read, completed_at=helpers.day(-2))

    rows = await collect_data()

    assert rows == [
        (helpers.day(-4), long_read, 1, long_log),
        (helpers.day(-3), short_read, 2, short_log),
        # still being read on the completion day
        (helpers.day(-2), short_read, 0, None),
        (helpers.day(-1), long_read, 0, None),
        (helpers.day(0), long_read, 0, None),
    ]


async def test_data_uses_the_given_records_and_completion_dates_without_reading_them(
    clock,
):
    stored = await h.reading(clock, started=helpers.day(-9))
    await db.insert_log_record(material_id=stored, count=99, date=helpers.day(-8))
    first = UUID(int=1)
    second = UUID(int=2)
    records = [
        db.LogRecord(date=helpers.day(-2), count=7, material_id=first),
        db.LogRecord(date=helpers.day(-1), count=8, material_id=second),
    ]

    rows = await collect_data(
        log_records=records,
        completion_dates={second: helpers.at(helpers.day(-1))},
    )

    assert rows == [
        (helpers.day(-2), first, 7, None),
        (helpers.day(-1), second, 8, None),
        (helpers.day(0), first, 0, None),
    ]


async def test_data_fails_when_completion_dates_cannot_be_read(clock, mocker):
    material_id = await h.completed(clock, started=helpers.day(-3), finished=helpers.day(-2))
    await db.insert_log_record(material_id=material_id, count=100, date=helpers.day(-2))
    mocker.patch.object(
        db,
        "get_completion_dates",
        side_effect=database.DatabaseException("down"),
    )

    with pytest.raises(database.DatabaseException, match="down"):
        await collect_data()


async def test_data_yields_nothing_when_every_log_is_after_today_current_behaviour(clock):
    material_id = await h.reading(clock, started=helpers.day(-3))
    await db.insert_log_record(material_id=material_id, count=4, date=helpers.day(1))

    assert await collect_data() == []


async def test_data_covers_days_after_the_only_material_is_completed(clock):
    material_id = await h.completed(clock, started=helpers.day(-3), finished=helpers.day(-2))
    await db.insert_log_record(material_id=material_id, count=100, date=helpers.day(-2))

    rows = await collect_data()

    assert [(date, count) for date, _, count, _ in rows] == [
        (helpers.day(-2), 100),
        (helpers.day(-1), 0),
        (helpers.day(0), 0),
    ]


# get_material_reading_now


async def test_material_reading_now_is_none_without_logs(clock):
    await h.reading(clock, started=helpers.day(-3))

    assert await db.get_material_reading_now() is None


async def test_material_reading_now_is_the_material_of_the_last_day(clock):
    history = await h.reading_history(clock)

    assert await db.get_material_reading_now() == history.article


async def test_material_reading_now_is_the_material_logged_today(clock):
    await h.reading_history(clock)
    material_id = await h.reading(clock, started=helpers.day(-1))
    await db.insert_log_record(material_id=material_id, count=1, date=helpers.day(0))

    assert await db.get_material_reading_now() == material_id


async def test_material_reading_now_falls_back_to_the_last_started_material(clock):
    completed_id = await h.completed(clock, started=helpers.day(-5), finished=helpers.day(-3))
    await db.insert_log_record(material_id=completed_id, count=100, date=helpers.day(-3))
    started_id = await h.reading(clock, started=helpers.day(-1))

    assert await db.get_material_reading_now() == started_id


# check_record_correct


@pytest.mark.parametrize(
    ("date", "count"),
    [(helpers.TODAY, 1), (helpers.day(-5), 1), (helpers.day(-2), 100)],
    ids=["today", "the start date", "every page at once"],
)
async def test_record_is_correct_for_a_reading_material(clock, date, count):
    material_id = await h.reading(clock, started=helpers.day(-5), pages=100)

    result = await db.check_record_correct(
        material_id=material_id, date=date, count=count
    )

    assert result is None


async def test_record_is_correct_when_it_reads_exactly_the_remaining_pages(clock):
    material_id = await h.reading(clock, started=helpers.day(-5), pages=100)
    await db.insert_log_record(material_id=material_id, count=60, date=helpers.day(-4))
    await db.insert_log_record(material_id=material_id, count=30, date=helpers.day(-3))

    assert (
        await db.check_record_correct(material_id=material_id, date=helpers.day(-2), count=10)
    ) is None


async def test_record_exceeding_the_remaining_pages_is_rejected(clock):
    material_id = await h.reading(clock, started=helpers.day(-5), pages=100)
    other_id = await h.reading(clock, started=helpers.day(-5), pages=100)
    await db.insert_log_record(material_id=material_id, count=60, date=helpers.day(-4))
    await db.insert_log_record(material_id=material_id, count=30, date=helpers.day(-3))
    await db.insert_log_record(material_id=other_id, count=1, date=helpers.day(-3))

    with pytest.raises(
        ValueError,
        match=r"^There are more pages than the material remains: "
        r"total pages read 90, material pages 100$",
    ):
        await db.check_record_correct(material_id=material_id, date=helpers.day(-2), count=11)


async def test_record_in_the_future_is_rejected(clock):
    material_id = await h.reading(clock, started=helpers.day(-5))

    with pytest.raises(ValueError, match=r"^Date could not be in the future$"):
        await db.check_record_correct(material_id=material_id, date=helpers.day(1), count=1)


@pytest.mark.parametrize("count", [0, -1], ids=["zero", "negative"])
async def test_record_without_a_positive_count_is_rejected(clock, count):
    material_id = await h.reading(clock, started=helpers.day(-5))

    with pytest.raises(ValueError, match=r"^Count must be greater than 0$"):
        await db.check_record_correct(material_id=material_id, date=helpers.day(-1), count=count)


@pytest.mark.parametrize("state", ["missing", "queued", "completed"])
async def test_record_of_a_material_not_being_read_is_rejected(clock, state):
    material_id = h.MISSING_ID
    if state == "queued":
        material_id = await h.queued(clock)
    if state == "completed":
        material_id = await h.completed(clock, started=helpers.day(-5), finished=helpers.day(-2))
    await h.reading(clock, started=helpers.day(-5))

    with pytest.raises(
        ValueError, match=rf"^No reading material id={material_id} found$"
    ):
        await db.check_record_correct(material_id=material_id, date=helpers.day(-1), count=1)


async def test_record_before_the_material_start_is_rejected(clock):
    material_id = await h.reading(clock, started=helpers.day(-5))

    with pytest.raises(
        ValueError,
        match=r"^Date 2024-03-09 is before the material start 2024-03-10 00:00:00$",
    ):
        await db.check_record_correct(material_id=material_id, date=helpers.day(-6), count=1)
