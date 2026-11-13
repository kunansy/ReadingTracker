import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from tests.unit.materials.helpers import day, midnight, uid
from tracker.reading_log import db


A, B, C = uid(0xA), uid(0xB), uid(0xC)

type Day = tuple[datetime.date, UUID, int]


def _log(material_id: UUID, offset: int, count: int = 10) -> db.LogRecord:
    return db.LogRecord(
        log_id=UUID(int=(material_id.int << 16) + offset + 1000),
        material_id=material_id,
        count=count,
        date=day(offset),
    )


async def _days(
    log_records: list[db.LogRecord] | None,
    completion_dates: dict[UUID | None, datetime.datetime] | None,
) -> list[Day]:
    return [
        (date, record.material_id, record.count)
        async for date, record in db.data(
            log_records=log_records,
            completion_dates=completion_dates,
        )
    ]


@pytest.fixture(autouse=True)
def _clock(frozen_now):
    return frozen_now


@pytest.fixture
def db_lookups(mocker):
    """Nothing is completed unless a test says otherwise.

    `data()` treats an empty `completion_dates` as "not passed" and loads them itself.
    """
    list_log_records = mocker.patch.object(
        db,
        "list_log_records",
        mocker.AsyncMock(return_value=[]),
    )
    get_completion_dates = mocker.patch.object(
        db,
        "get_completion_dates",
        mocker.AsyncMock(return_value={}),
    )
    return list_log_records, get_completion_dates


async def test_single_log_today_gives_one_day(db_lookups):
    record = _log(A, 0, 25)

    result = [item async for item in db.data(log_records=[record])]

    assert result == [(day(0), record)]


async def test_days_after_the_last_log_are_filled_with_the_material_up_to_today(db_lookups):
    result = [item async for item in db.data(log_records=[_log(A, -2, 7)])]

    assert [(date, r.material_id, r.count, r.log_id is None) for date, r in result] == [
        (day(-2), A, 7, False),
        (day(-1), A, 0, True),
        (day(0), A, 0, True),
    ]
    assert [record.date for _, record in result] == [day(-2), day(-1), day(0)]


async def test_gaps_between_logs_are_filled_with_the_same_material(db_lookups):
    days = await _days([_log(A, -4, 10), _log(A, -2, 5)], None)

    assert days == [
        (day(-4), A, 10),
        (day(-3), A, 0),
        (day(-2), A, 5),
        (day(-1), A, 0),
        (day(0), A, 0),
    ]


@pytest.mark.parametrize(
    "records",
    [
        [_log(A, -3), _log(A, -1), _log(A, 0)],
        [_log(A, 0), _log(A, -1), _log(A, -3)],
        [_log(A, -1), _log(A, -3), _log(A, 0)],
    ],
    ids=["ascending", "descending-as-the-db-returns", "shuffled"],
)
async def test_days_are_yielded_in_date_order_whatever_the_input_order(db_lookups, records):
    days = await _days(records, None)

    assert days == [(day(-3), A, 10), (day(-2), A, 0), (day(-1), A, 10), (day(0), A, 10)]


async def test_empty_days_belong_to_the_material_started_last(db_lookups):
    days = await _days([_log(A, -3), _log(B, -2)], None)

    assert days == [(day(-3), A, 10), (day(-2), B, 10), (day(-1), B, 0), (day(0), B, 0)]


async def test_completed_material_is_popped_and_the_previous_one_continues():
    days = await _days([_log(A, -4), _log(B, -3)], {B: midnight(-3)})

    assert days == [
        (day(-4), A, 10),
        (day(-3), B, 10),
        (day(-2), A, 0),
        (day(-1), A, 0),
        (day(0), A, 0),
    ]


async def test_empty_completion_day_still_belongs_to_the_completed_material():
    days = await _days([_log(A, -4), _log(B, -3)], {B: midnight(-2)})

    assert days[2:] == [(day(-2), B, 0), (day(-1), A, 0), (day(0), A, 0)]


async def test_completion_time_of_day_does_not_matter():
    completed_at = midnight(-3).replace(hour=23, minute=59, second=59)

    days = await _days([_log(A, -4), _log(B, -3)], {B: completed_at})

    assert days[2] == (day(-2), A, 0)


async def test_material_completed_today_keeps_today():
    days = await _days([_log(A, -2), _log(B, -1)], {B: midnight(0)})

    assert days == [(day(-2), A, 10), (day(-1), B, 10), (day(0), B, 0)]


async def test_several_materials_completed_on_one_day_are_all_popped():
    days = await _days(
        [_log(A, -5), _log(B, -4), _log(C, -3)],
        {B: midnight(-3), C: midnight(-3)},
    )

    assert days[3:] == [(day(-2), A, 0), (day(-1), A, 0), (day(0), A, 0)]


async def test_completion_of_a_material_under_the_top_is_applied_once_it_surfaces():
    days = await _days(
        [_log(A, -5), _log(B, -4), _log(C, -3)],
        {B: midnight(-4), C: midnight(-2)},
    )

    assert days == [
        (day(-5), A, 10),
        (day(-4), B, 10),
        (day(-3), C, 10),
        (day(-2), C, 0),
        (day(-1), A, 0),
        (day(0), A, 0),
    ]


async def test_returning_to_an_earlier_material_moves_it_to_the_top(db_lookups):
    days = await _days([_log(A, -4), _log(B, -3), _log(A, -2)], None)

    assert days[2:] == [(day(-2), A, 10), (day(-1), A, 0), (day(0), A, 0)]


async def test_material_returned_to_and_then_completed_gives_way_to_the_other_one():
    days = await _days([_log(A, -4), _log(B, -3), _log(A, -2)], {A: midnight(-2)})

    assert days[2:] == [(day(-2), A, 10), (day(-1), B, 0), (day(0), B, 0)]


@pytest.mark.parametrize(
    ("first", "second"),
    [(A, B), (B, A)],
    ids=["a-then-b", "b-then-a"],
)
async def test_several_materials_logged_on_one_day_are_all_yielded(db_lookups, first, second):
    days = await _days([_log(first, -1, 3), _log(second, -1, 4)], None)

    assert days == [(day(-1), first, 3), (day(-1), second, 4), (day(0), second, 0)]


async def test_material_logged_again_with_another_one_on_the_same_day(db_lookups):
    days = await _days([_log(A, -3), _log(B, -2), _log(B, -1, 1), _log(A, -1, 2)], None)

    assert days == [
        (day(-3), A, 10),
        (day(-2), B, 10),
        (day(-1), B, 1),
        (day(-1), A, 2),
        (day(0), A, 0),
    ]


async def test_log_of_the_next_material_on_the_day_after_completion():
    days = await _days([_log(A, -2), _log(B, -1)], {A: midnight(-2)})

    assert days == [(day(-2), A, 10), (day(-1), B, 10), (day(0), B, 0)]


async def test_future_logs_are_not_yielded(db_lookups):
    days = await _days([_log(A, -1), _log(A, 1), _log(B, 30)], None)

    assert days == [(day(-1), A, 10), (day(0), A, 0)]


async def test_only_future_logs_give_nothing(db_lookups):
    assert await _days([_log(A, 1)], None) == []


async def test_long_gap_is_filled_day_by_day(db_lookups):
    days = await _days([_log(A, -400)], None)

    assert len(days) == 401
    assert [date for date, _, _ in days] == [day(offset) for offset in range(-400, 1)]
    assert {(material_id, count) for _, material_id, count in days[1:]} == {(A, 0)}


async def test_logs_and_completion_dates_are_loaded_when_not_passed(db_lookups):
    list_log_records, get_completion_dates = db_lookups
    list_log_records.return_value = [_log(A, -2), _log(B, -1)]
    get_completion_dates.return_value = {B: midnight(-1)}

    days = await _days(None, None)

    assert days == [(day(-2), A, 10), (day(-1), B, 10), (day(0), A, 0)]
    list_log_records.assert_awaited_once_with()
    get_completion_dates.assert_awaited_once_with()


async def test_passed_logs_and_completion_dates_are_not_loaded(db_lookups):
    list_log_records, get_completion_dates = db_lookups

    await _days([_log(A, -1), _log(B, 0)], {B: midnight(0)})

    list_log_records.assert_not_awaited()
    get_completion_dates.assert_not_awaited()


async def test_empty_log_in_the_database_gives_nothing(db_lookups):
    list_log_records, get_completion_dates = db_lookups

    assert await _days(None, None) == []
    get_completion_dates.assert_not_awaited()


async def test_failed_completion_dates_lookup_is_treated_as_nothing_completed(db_lookups):
    _, get_completion_dates = db_lookups
    get_completion_dates.side_effect = RuntimeError("database is down")

    days = await _days([_log(A, -2), _log(B, -1)], None)

    assert days == [(day(-2), A, 10), (day(-1), B, 10), (day(0), B, 0)]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: tracker/reading_log/db.py:141 `log_records or await list_log_records()` "
        "treats an explicitly passed [] as not passed and reads the whole log from the db"
    ),
)
async def test_explicit_empty_log_gives_nothing_without_reading_the_database(db_lookups):
    list_log_records, _ = db_lookups
    list_log_records.return_value = [_log(A, 0)]

    days = await _days([], {})

    assert days == []
    list_log_records.assert_not_awaited()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: tracker/reading_log/db.py:151 `completion_dates or await get_completion_dates()` "
        "treats an explicitly passed {} as not passed and replaces it with the db values"
    ),
)
async def test_explicit_empty_completion_dates_are_not_replaced_by_the_database(db_lookups):
    _, get_completion_dates = db_lookups
    get_completion_dates.return_value = {B: midnight(-1)}

    days = await _days([_log(A, -2), _log(B, -1)], {})

    get_completion_dates.assert_not_awaited()
    assert days[-1] == (day(0), B, 0)


@pytest.mark.xfail(
    strict=True,
    raises=ValidationError,
    reason=(
        "BUG: tracker/reading_log/db.py:170-171 an empty day when every earlier material "
        "is completed builds LogRecord(material_id=None), which fails validation"
    ),
)
@pytest.mark.parametrize(
    ("records", "completion_dates", "logged_days"),
    [
        ([_log(A, -2)], {A: midnight(-2)}, [(day(-2), A, 10)]),
        (
            [_log(A, -3), _log(B, 0)],
            {A: midnight(-3)},
            [(day(-3), A, 10), (day(0), B, 10)],
        ),
        (
            [_log(A, -4), _log(B, -3)],
            {A: midnight(-3), B: midnight(-3)},
            [(day(-4), A, 10), (day(-3), B, 10)],
        ),
    ],
    ids=["nothing-read-since-completion", "gap-before-the-next-material", "stack-emptied"],
)
async def test_days_without_any_material_being_read_do_not_break_the_log(
    records,
    completion_dates,
    logged_days,
):
    days = await _days(records, completion_dates)

    assert [item for item in days if item[2]] == logged_days
