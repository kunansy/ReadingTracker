from types import SimpleNamespace

import pytest

from tests.unit.materials.helpers import compile_sql, day, make_material, midnight, uid
from tracker.common import database, pagination
from tracker.common.sort_keys import SEPARATOR
from tracker.materials import db as materials_db
from tracker.reading_log import db


MATERIAL_ID = uid(1)
LOG_COLUMNS = (
    "SELECT reading_log.log_id, reading_log.material_id, reading_log.count, "
    "reading_log.date, reading_log.sort_key FROM reading_log"
)


@pytest.mark.parametrize(
    ("lst", "index", "default", "expected"),
    [
        ([], 0, None, None),
        ([], -1, None, None),
        ([], 1, -1, -1),
        ([1], 0, -1, 1),
        ([1], 1, -1, -1),
        ([1], -1, -1, 1),
        ([1], -2, -1, -1),
        ([3, 4, 5], -1, -1, 5),
        ([3, 4, 5], 2, -1, 5),
        ([3, 4, 5], 3, -1, -1),
        ([None], 0, "default", None),
    ],
    ids=[
        "empty-first",
        "empty-last",
        "empty-with-default",
        "first",
        "one-past-the-end",
        "last",
        "one-before-the-start",
        "negative-index",
        "last-by-index",
        "past-the-end",
        "stored-none-is-returned",
    ],
)
def test_safe_list_get(lst, index, default, expected):
    assert db._safe_list_get(lst, index, default) == expected


def test_safe_list_get_default_is_none():
    assert db._safe_list_get([], 5) is None


def test_log_records_without_filters_are_ordered_by_date_desc():
    assert compile_sql(db._list_log_records_stmt()) == (
        f"{LOG_COLUMNS} ORDER BY reading_log.date DESC"
    )


@pytest.mark.parametrize(
    ("filters", "expected_where"),
    [
        ({"material_id": MATERIAL_ID}, f"reading_log.material_id = '{MATERIAL_ID}'"),
        ({"from_date": day(-1)}, "reading_log.date >= '2024-03-09'"),
        ({"to_date": day(0)}, "reading_log.date <= '2024-03-10'"),
        (
            {"from_date": day(0), "to_date": day(0)},
            "reading_log.date >= '2024-03-10' AND reading_log.date <= '2024-03-10'",
        ),
        (
            {"material_id": MATERIAL_ID, "from_date": day(-1), "to_date": day(0)},
            f"reading_log.material_id = '{MATERIAL_ID}' "
            "AND reading_log.date >= '2024-03-09' AND reading_log.date <= '2024-03-10'",
        ),
    ],
    ids=["material", "from-inclusive", "to-inclusive", "one-day-range", "all-filters"],
)
def test_log_records_filters(filters, expected_where):
    assert compile_sql(db._list_log_records_stmt(**filters)) == (
        f"{LOG_COLUMNS} WHERE {expected_where} ORDER BY reading_log.date DESC"
    )


def _reading_material(**overrides):
    fields = {"material_id": MATERIAL_ID, "pages": 100, "started_at": midnight(-5)}
    return make_material(**(fields | overrides))


def _logs(*counts: int) -> list[db.LogRecord]:
    return [
        db.LogRecord(material_id=MATERIAL_ID, count=count, date=day(-index - 1))
        for index, count in enumerate(counts)
    ]


@pytest.fixture
def lookups(mocker, frozen_now):
    return SimpleNamespace(
        get_reading_materials=mocker.patch.object(
            materials_db,
            "get_reading_materials",
            mocker.AsyncMock(
                return_value=[
                    _reading_material(material_id=uid(2), pages=1),
                    _reading_material(),
                ],
            ),
        ),
        list_log_records=mocker.patch.object(
            db,
            "list_log_records",
            mocker.AsyncMock(return_value=_logs(60, 30)),
        ),
    )


@pytest.mark.parametrize(
    ("date", "count"),
    [(day(0), 1), (day(-5), 1), (day(-1), 10), (day(-1), 9)],
    ids=["today", "on-the-start-day", "exactly-the-remaining-pages", "below-the-remaining"],
)
async def test_valid_record_is_accepted(lookups, date, count):
    await db.check_record_correct(material_id=MATERIAL_ID, date=date, count=count)

    lookups.get_reading_materials.assert_awaited_once_with()
    lookups.list_log_records.assert_awaited_once_with(material_id=MATERIAL_ID)


async def test_first_record_may_cover_the_whole_material(lookups):
    lookups.list_log_records.return_value = []

    await db.check_record_correct(material_id=MATERIAL_ID, date=day(0), count=100)


@pytest.mark.parametrize("offset", [1, 400], ids=["tomorrow", "far-future"])
async def test_future_date_is_rejected_before_any_lookup(lookups, offset):
    with pytest.raises(ValueError, match="^Date could not be in the future$"):
        await db.check_record_correct(material_id=MATERIAL_ID, date=day(offset), count=1)

    lookups.get_reading_materials.assert_not_awaited()
    lookups.list_log_records.assert_not_awaited()


@pytest.mark.parametrize("count", [0, -1, -100])
async def test_non_positive_count_is_rejected_before_any_lookup(lookups, count):
    with pytest.raises(ValueError, match="^Count must be greater than 0$"):
        await db.check_record_correct(material_id=MATERIAL_ID, date=day(0), count=count)

    lookups.get_reading_materials.assert_not_awaited()


@pytest.mark.parametrize(
    "reading",
    [[], [_reading_material(material_id=uid(2))]],
    ids=["nothing-is-read", "another-material-is-read"],
)
async def test_material_that_is_not_being_read_is_rejected(lookups, reading):
    lookups.get_reading_materials.return_value = reading

    with pytest.raises(ValueError, match=f"^No reading material id={MATERIAL_ID} found$"):
        await db.check_record_correct(material_id=MATERIAL_ID, date=day(0), count=1)


async def test_material_without_start_date_is_rejected(lookups):
    lookups.get_reading_materials.return_value = [_reading_material(started_at=None)]

    with pytest.raises(ValueError, match=f"^Material id={MATERIAL_ID} is not started$"):
        await db.check_record_correct(material_id=MATERIAL_ID, date=day(0), count=1)


async def test_date_before_the_material_start_is_rejected(lookups):
    with pytest.raises(ValueError, match="^Date 2024-03-04 is before the material start"):
        await db.check_record_correct(material_id=MATERIAL_ID, date=day(-6), count=1)


async def test_date_of_start_is_compared_without_time_of_day(lookups):
    lookups.get_reading_materials.return_value = [
        _reading_material(started_at=midnight(-5).replace(hour=18)),
    ]

    await db.check_record_correct(material_id=MATERIAL_ID, date=day(-5), count=1)


@pytest.mark.parametrize("count", [11, 1000], ids=["one-page-over", "far-over"])
async def test_more_pages_than_remain_is_rejected(lookups, count):
    with pytest.raises(
        ValueError,
        match=(
            "^There are more pages than the material remains: "
            "total pages read 90, material pages 100$"
        ),
    ):
        await db.check_record_correct(material_id=MATERIAL_ID, date=day(0), count=count)


async def test_record_for_an_already_logged_date_is_accepted_current_behaviour(lookups):
    """The (material_id, date) uniqueness is left to the `uix_reading_log` constraint."""
    await db.check_record_correct(material_id=MATERIAL_ID, date=day(-1), count=1)


def _data_of(*material_ids):
    async def _data():
        for index, material_id in enumerate(material_ids):
            yield day(index - len(material_ids)), SimpleNamespace(material_id=material_id)

    return _data


@pytest.fixture
def reading_now(mocker):
    return SimpleNamespace(
        is_log_empty=mocker.patch.object(
            db,
            "is_log_empty",
            mocker.AsyncMock(return_value=False),
        ),
        get_last_material_started=mocker.patch.object(
            materials_db,
            "get_last_material_started",
            mocker.AsyncMock(return_value=uid(9)),
        ),
    )


async def test_nothing_is_read_now_when_the_log_is_empty(mocker, reading_now):
    reading_now.is_log_empty.return_value = True
    data = mocker.patch.object(db, "data")

    assert await db.get_material_reading_now() is None
    data.assert_not_called()
    reading_now.get_last_material_started.assert_not_awaited()


async def test_material_of_the_last_log_day_is_read_now(mocker, reading_now):
    mocker.patch.object(db, "data", _data_of(uid(1), uid(2), uid(3)))

    assert await db.get_material_reading_now() == uid(3)
    reading_now.get_last_material_started.assert_not_awaited()


async def test_last_started_material_is_assumed_when_no_day_is_yielded(mocker, reading_now):
    mocker.patch.object(db, "data", _data_of())

    assert await db.get_material_reading_now() == uid(9)
    reading_now.get_last_material_started.assert_awaited_once_with()


async def test_nothing_is_read_now_when_nothing_was_started(mocker, reading_now):
    mocker.patch.object(db, "data", _data_of())
    reading_now.get_last_material_started.return_value = None

    assert await db.get_material_reading_now() is None


@pytest.mark.parametrize("material_id", [MATERIAL_ID, None], ids=["material", "all"])
async def test_log_records_page_is_bound_to_the_material_filter(mocker, material_id):
    expected = pagination.Page(items=[], next_token=None, total_count=0)
    fetch_page = mocker.patch.object(
        pagination,
        "fetch_page",
        mocker.AsyncMock(return_value=expected),
    )

    page = await db.list_log_records_page(
        material_id=material_id,
        params=pagination.PageParams(page_size=2),
    )

    assert page is expected
    kwargs = fetch_page.await_args.kwargs
    assert compile_sql(fetch_page.await_args.args[0]) == compile_sql(
        db._list_log_records_stmt(material_id=material_id),
    )
    assert kwargs["request"].params == {
        "order": "desc",
        "max_items": "2",
        "material_id": str(material_id) if material_id else "",
    }
    key = kwargs["cursor_expr"]
    assert compile_sql(key.text) == (
        f"to_char(reading_log.date, 'YYYY-MM-DD') || '{SEPARATOR}' "
        '|| reading_log.sort_key COLLATE "C"'
    )
    assert [part.column.name for part in key.parts] == ["date", "sort_key"]
    row = SimpleNamespace(log_id=uid(5), material_id=MATERIAL_ID, count=3, date=day(0))
    assert kwargs["to_item"](row) == db.LogRecord(
        log_id=uid(5),
        material_id=MATERIAL_ID,
        count=3,
        date=day(0),
    )


async def test_log_records_page_rejects_token_of_another_material(mocker):
    fetch_page = mocker.patch.object(pagination, "fetch_page", mocker.AsyncMock())
    token = pagination.encode_next_token(
        {"order": "desc", "max_items": "20", "material_id": str(uid(2))},
        {"cursor": "c"},
    )

    with pytest.raises(database.InvalidNextTokenException):
        await db.list_log_records_page(
            material_id=MATERIAL_ID,
            params=pagination.PageParams(next_token=token),
        )

    fetch_page.assert_not_awaited()
