import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from tests.unit.materials.helpers import TODAY, compile_sql, day, make_material, midnight, uid
from tracker.common import database, pagination
from tracker.common.sort_keys import SEPARATOR
from tracker.materials import db
from tracker.models import enums
from tracker.notes import db as notes_db
from tracker.reading_log import statistics


def _log_stat(material_id=None, **overrides) -> statistics.LogStatistics:
    fields = {
        "material_id": material_id or uid(1),
        "total": 40,
        "lost_time": 1,
        "duration": 2,
        "min_record": database.MinMax(count=15, date=day(-3)),
        "max_record": database.MinMax(count=25, date=day(-1)),
    }
    return statistics.LogStatistics(**(fields | overrides))


def _statistics(**overrides) -> db.MaterialStatistics:
    fields = {
        "material": make_material(started_at=midnight(-3)),
        "started_at": day(-3),
        "duration": 2,
        "lost_time": 1,
        "total": 40,
        "min_record": None,
        "max_record": None,
        "mean": 20,
        "notes_count": 0,
    }
    return db.MaterialStatistics(**(fields | overrides))


@pytest.mark.parametrize(
    ("total", "pages", "expected"),
    [
        (0, 100, 0.0),
        (40, 100, 40.0),
        (100, 100, 100.0),
        (1, 3, 33.33),
        (2, 3, 66.67),
        (150, 100, 150.0),
        (0, 0, 0.0),
        (5, 0, 0.0),
    ],
    ids=[
        "nothing-read",
        "partially-read",
        "fully-read",
        "rounds-down",
        "rounds-up",
        "more-read-than-pages",
        "zero-pages",
        "zero-pages-with-total",
    ],
)
def test_percent_completed(total, pages, expected):
    stat = _statistics(material=make_material(pages=pages), total=total)

    assert stat.percent_completed == expected
    assert stat.model_dump()["percent_completed"] == expected


def test_statistics_of_not_started_material_is_rejected():
    with pytest.raises(ValueError, match="is not started"):
        db._get_material_statistics(
            material=make_material(started_at=None),
            notes_count=0,
            mean_total=Decimal(1),
            log_stats={},
        )


def test_statistics_of_reading_material_without_log_uses_overall_mean(frozen_now):
    material = make_material(pages=100, started_at=midnight(0))

    result = db._get_material_statistics(
        material=material,
        notes_count=10,
        mean_total=Decimal("33.4"),
        log_stats={},
    )

    assert result == db.MaterialStatistics(
        material=material,
        started_at=TODAY,
        completed_at=None,
        total_reading_duration="1 days",
        duration=0,
        lost_time=0,
        total=0,
        min_record=None,
        max_record=None,
        mean=33,
        notes_count=10,
        remaining_pages=100,
        remaining_days=3,
        would_be_completed=day(3),
    )
    assert result.percent_completed == 0.0


def test_statistics_ignore_log_of_another_material(frozen_now):
    material = make_material(material_id=uid(1), pages=10, started_at=midnight(-1))

    result = db._get_material_statistics(
        material=material,
        notes_count=0,
        mean_total=Decimal(5),
        log_stats={uid(2): _log_stat(uid(2))},
    )

    assert result.total == 0
    assert result.mean == 5
    assert result.remaining_days == 2


def test_statistics_of_reading_material_with_log(frozen_now):
    material = make_material(pages=100, started_at=midnight(-3))
    log_stat = _log_stat()

    result = db._get_material_statistics(
        material=material,
        notes_count=4,
        mean_total=Decimal(999),
        log_stats={material.material_id: log_stat},
    )

    assert result.mean == 20
    assert result.total == 40
    assert result.duration == 2
    assert result.lost_time == 1
    assert result.min_record == log_stat.min_record
    assert result.max_record == log_stat.max_record
    assert result.remaining_pages == 60
    assert result.remaining_days == 3
    assert result.would_be_completed == day(3)
    assert result.total_reading_duration == "4 days"
    assert result.notes_count == 4
    assert result.percent_completed == 40.0


def test_statistics_of_fully_read_but_not_completed_material(frozen_now):
    material = make_material(pages=40, started_at=midnight(-3))

    result = db._get_material_statistics(
        material=material,
        notes_count=0,
        mean_total=Decimal(1),
        log_stats={material.material_id: _log_stat()},
    )

    assert result.remaining_pages == 0
    assert result.remaining_days == 0
    assert result.would_be_completed == TODAY


def test_statistics_of_completed_material_has_no_forecast(mocker):
    utcnow = mocker.patch.object(database, "utcnow")
    material = make_material(
        pages=40,
        started_at=midnight(-30),
        completed_at=midnight(-1),
    )

    result = db._get_material_statistics(
        material=material,
        notes_count=2,
        mean_total=Decimal(1),
        log_stats={material.material_id: _log_stat()},
    )

    assert result.completed_at == day(-1)
    assert result.remaining_pages is None
    assert result.remaining_days is None
    assert result.would_be_completed is None
    assert result.total_reading_duration == "1 months"
    assert result.percent_completed == 100.0
    utcnow.assert_not_called()


def test_statistics_of_completed_material_without_log():
    material = make_material(started_at=midnight(-1), completed_at=midnight(-1))

    result = db._get_material_statistics(
        material=material,
        notes_count=0,
        mean_total=Decimal("0.2"),
        log_stats={},
    )

    assert result.mean == 0
    assert result.total == 0
    assert result.total_reading_duration == "1 days"


def test_more_pages_read_than_material_has_gives_negative_forecast_current_behaviour(
    frozen_now,
):
    material = make_material(pages=30, started_at=midnight(-3))

    result = db._get_material_statistics(
        material=material,
        notes_count=0,
        mean_total=Decimal(1),
        log_stats={material.material_id: _log_stat()},
    )

    assert result.remaining_pages == -10
    assert result.remaining_days == 0
    assert result.would_be_completed == TODAY
    assert result.percent_completed == 133.33


@pytest.mark.parametrize(
    ("mean_total", "log_stats"),
    [
        (Decimal("0.4"), {}),
        (Decimal(0), {}),
        (Decimal(50), {uid(1): _log_stat(total=0, duration=0, lost_time=3)}),
    ],
    ids=["overall-mean-rounds-to-zero", "overall-mean-is-zero", "log-of-empty-records"],
)
def test_zero_mean_of_reading_material_divides_by_zero_current_behaviour(
    frozen_now,
    mean_total,
    log_stats,
):
    material = make_material(material_id=uid(1), started_at=midnight(-3))

    with pytest.raises(ZeroDivisionError):
        db._get_material_statistics(
            material=material,
            notes_count=0,
            mean_total=mean_total,
            log_stats=log_stats,
        )


def test_start_with_time_of_day_is_rejected_by_statistics_model_current_behaviour(
    frozen_now,
):
    material = make_material(started_at=midnight(-1).replace(hour=9))

    with pytest.raises(ValidationError, match="started_at"):
        db._get_material_statistics(
            material=material,
            notes_count=0,
            mean_total=Decimal(1),
            log_stats={},
        )


@pytest.fixture
def statistics_sources(mocker):
    return SimpleNamespace(
        get_means=mocker.patch.object(
            db,
            "get_means",
            mocker.AsyncMock(return_value={enums.MaterialTypesEnum.book: Decimal("20.4")}),
        ),
        notes_count=mocker.patch.object(
            notes_db,
            "get_all_notes_count",
            mocker.AsyncMock(return_value={uid(1): 3}),
        ),
        materials_stat=mocker.patch.object(
            statistics,
            "calculate_materials_stat",
            mocker.AsyncMock(return_value={uid(1): _log_stat(uid(1))}),
        ),
    )


async def test_materials_statistics_combines_log_notes_and_means(
    frozen_now,
    statistics_sources,
):
    book = make_material(material_id=uid(1), pages=100, started_at=midnight(-3))
    article = make_material(
        material_id=uid(2),
        title="Статья",
        pages=7,
        material_type=enums.MaterialTypesEnum.article,
        started_at=midnight(0),
    )

    result = await db._get_materials_statistics([book, article])

    assert [stat.material for stat in result] == [book, article]
    book_stat, article_stat = result
    assert (book_stat.total, book_stat.mean, book_stat.notes_count) == (40, 20, 3)
    assert (book_stat.remaining_pages, book_stat.remaining_days) == (60, 3)
    # no log, no notes and no mean for articles: one page a day is assumed
    assert (article_stat.total, article_stat.mean, article_stat.notes_count) == (0, 1, 0)
    assert (article_stat.remaining_pages, article_stat.remaining_days) == (7, 7)
    assert article_stat.would_be_completed == day(7)
    statistics_sources.materials_stat.assert_awaited_once_with({uid(1), uid(2)})
    statistics_sources.get_means.assert_awaited_once_with()
    statistics_sources.notes_count.assert_awaited_once_with()


async def test_materials_statistics_uses_type_mean_for_material_without_log(
    frozen_now,
    statistics_sources,
):
    book = make_material(material_id=uid(5), pages=100, started_at=midnight(0))

    [stat] = await db._get_materials_statistics([book])

    assert stat.mean == 20
    assert stat.remaining_days == 5


async def test_materials_statistics_of_no_materials(statistics_sources):
    assert await db._get_materials_statistics([]) == []
    statistics_sources.materials_stat.assert_awaited_once_with(set())


async def test_get_means_delegates_to_reading_log_statistics(mocker):
    means = {enums.MaterialTypesEnum.lecture: Decimal("12.5")}
    get_means = mocker.patch.object(
        statistics,
        "get_means",
        mocker.AsyncMock(return_value=means),
    )

    assert await db.get_means() == means
    get_means.assert_awaited_once_with()


async def test_reading_statistics_are_calculated_for_reading_materials(mocker):
    materials = [make_material(started_at=midnight(-1))]
    stats = [_statistics()]
    get_reading = mocker.patch.object(
        db,
        "get_reading_materials",
        mocker.AsyncMock(return_value=materials),
    )
    calculate = mocker.patch.object(
        db,
        "_get_materials_statistics",
        mocker.AsyncMock(return_value=stats),
    )

    assert await db.reading_statistics() == stats
    get_reading.assert_awaited_once_with()
    calculate.assert_awaited_once_with(materials)


@pytest.mark.parametrize(
    ("remaining_days", "expected"),
    [
        ([], TODAY),
        ([3], day(3)),
        ([3, 0, 10], day(13)),
        ([None, 4], day(4)),
        ([None], TODAY),
    ],
    ids=["nothing-is-read", "single", "sum", "none-is-skipped", "only-none"],
)
async def test_end_of_reading_adds_remaining_days_of_every_material(
    mocker,
    frozen_now,
    remaining_days,
    expected,
):
    stats = [_statistics(remaining_days=days) for days in remaining_days]
    mocker.patch.object(db, "reading_statistics", mocker.AsyncMock(return_value=stats))

    assert await db._end_of_reading() == expected


async def test_completed_statistics_of_missing_material_raises_not_found(mocker):
    parse = mocker.patch.object(
        db,
        "_parse_materials_response",
        mocker.AsyncMock(return_value=[]),
    )
    calculate = mocker.patch.object(db, "_get_materials_statistics", mocker.AsyncMock())

    with pytest.raises(database.NotFoundException, match="Completed material id=.* not found"):
        await db.get_completed_statistics(material_id=uid(9))

    sql = compile_sql(parse.await_args.kwargs["stmt"])
    assert "materials.completed_at IS NOT NULL" in sql
    assert f"materials.material_id = '{uid(9)}'" in sql
    calculate.assert_not_awaited()


async def test_completed_statistics_of_found_material(mocker):
    material = make_material(started_at=midnight(-5), completed_at=midnight(-1))
    stat = _statistics(material=material)
    mocker.patch.object(
        db,
        "_parse_materials_response",
        mocker.AsyncMock(return_value=[material]),
    )
    calculate = mocker.patch.object(
        db,
        "_get_materials_statistics",
        mocker.AsyncMock(return_value=[stat]),
    )

    assert await db.get_completed_statistics(material_id=material.material_id) is stat
    calculate.assert_awaited_once_with([material])


class _Row:
    def __init__(self, material: db.Material, **extra) -> None:
        self._fields = material.model_dump() | extra

    def _asdict(self) -> dict:
        return self._fields


@pytest.fixture
def fetch_page(mocker):
    return mocker.patch.object(pagination, "fetch_page", mocker.AsyncMock())


async def test_completed_statistics_page_binds_filters_and_replaces_items(mocker, fetch_page):
    material = make_material(started_at=midnight(-5), completed_at=midnight(-1))
    stat = _statistics(material=material)
    fetch_page.return_value = pagination.Page(
        items=[material],
        next_token="next",
        total_count=7,
    )
    calculate = mocker.patch.object(
        db,
        "_get_materials_statistics",
        mocker.AsyncMock(return_value=[stat]),
    )

    page = await db.completed_statistics_page(
        material_type=enums.MaterialTypesEnum.book,
        is_outlined=True,
        tags={"sql", "python"},
        params=pagination.PageParams(page_size=5),
    )

    assert page == pagination.Page(items=[stat], next_token="next", total_count=7)
    calculate.assert_awaited_once_with([material])
    stmt = fetch_page.await_args.args[0]
    kwargs = fetch_page.await_args.kwargs
    assert kwargs["request"].params == {
        "order": "desc",
        "max_items": "5",
        "material_type": "book",
        "is_outlined": "True",
        "tags": "python,sql",
    }
    assert kwargs["request"].order == pagination.Order.DESC
    assert compile_sql(stmt) == compile_sql(
        db._get_completed_materials_stmt(
            material_type=enums.MaterialTypesEnum.book,
            is_outlined=True,
            tags={"sql", "python"},
        ),
    )
    assert compile_sql(kwargs["cursor_expr"]) == (
        "to_char(materials.completed_at, 'YYYY-MM-DD\"T\"HH24:MI:SS.US') "
        f"|| '{SEPARATOR}' || materials.sort_key COLLATE \"C\""
    )
    # the extra pagination columns of the row must not break the model
    assert kwargs["to_item"](_Row(material, sort_key="k", cursor="c")) == material


async def test_completed_statistics_page_without_filters_keeps_requested_order(
    mocker,
    fetch_page,
):
    fetch_page.return_value = pagination.Page(items=[], next_token=None, total_count=0)
    mocker.patch.object(db, "_get_materials_statistics", mocker.AsyncMock(return_value=[]))

    page = await db.completed_statistics_page(
        params=pagination.PageParams(order=pagination.Order.ASC),
    )

    assert page == pagination.Page(items=[], next_token=None, total_count=0)
    assert fetch_page.await_args.kwargs["request"].params == {
        "order": "asc",
        "max_items": "20",
        "material_type": "",
        "is_outlined": "",
        "tags": "",
    }


async def test_completed_statistics_page_rejects_token_of_other_filters(fetch_page):
    token = pagination.encode_next_token(
        {
            "order": "desc",
            "max_items": "20",
            "material_type": "",
            "is_outlined": "",
            "tags": "",
        },
        {"cursor": "c"},
    )

    with pytest.raises(database.InvalidNextTokenException):
        await db.completed_statistics_page(
            is_outlined=True,
            params=pagination.PageParams(next_token=token),
        )

    fetch_page.assert_not_awaited()


async def test_reading_statistics_page_orders_by_last_read_date(mocker, fetch_page):
    material = make_material(started_at=midnight(-5))
    stat = _statistics(material=material)
    fetch_page.return_value = pagination.Page(
        items=[material],
        next_token=None,
        total_count=1,
    )
    calculate = mocker.patch.object(
        db,
        "_get_materials_statistics",
        mocker.AsyncMock(return_value=[stat]),
    )

    page = await db.reading_statistics_page(params=pagination.PageParams())

    assert page == pagination.Page(items=[stat], next_token=None, total_count=1)
    calculate.assert_awaited_once_with([material])
    stmt = fetch_page.await_args.args[0]
    kwargs = fetch_page.await_args.kwargs
    assert compile_sql(stmt) == compile_sql(db._get_reading_materials_stmt())
    assert kwargs["request"].params == {"order": "desc", "max_items": "20"}
    assert compile_sql(kwargs["cursor_expr"]) == (
        "to_char(coalesce(reading_logs.date, date(materials.started_at)), 'YYYY-MM-DD') "
        f"|| '{SEPARATOR}' || materials.sort_key COLLATE \"C\""
    )
    row = _Row(material, last_read_at=datetime.date(2024, 3, 9), sort_key="k")
    assert kwargs["to_item"](row) == material


async def test_repeating_queue_page_is_fetched_in_repeat_date_order(fetch_page):
    expected = pagination.Page(items=[], next_token=None, total_count=0)
    fetch_page.return_value = expected

    page = await db.get_repeating_queue_page(
        is_outlined=True,
        params=pagination.PageParams(page_size=3),
    )

    assert page is expected
    stmt = fetch_page.await_args.args[0]
    kwargs = fetch_page.await_args.kwargs
    assert kwargs["request"].order == pagination.Order.ASC
    assert kwargs["request"].params == {
        "order": "asc",
        "max_items": "3",
        "is_outlined": "True",
    }
    assert kwargs["to_item"] is db._to_repeating_queue
    assert compile_sql(stmt) == compile_sql(db._get_repeating_queue_stmt(is_outlined=True)[0])
    assert compile_sql(kwargs["cursor_expr"]) == (
        "to_char(date(coalesce(repeats_stat.last_repeated_at, materials.completed_at)) "
        "+ 30 * CAST(coalesce(repeats_stat.repeats_count, 0) AS INTEGER), 'YYYY-MM-DD') "
        f"|| '{SEPARATOR}' || materials.sort_key COLLATE \"C\""
    )


async def test_repeating_queue_page_rejects_token_of_another_outlined_filter(fetch_page):
    token = pagination.encode_next_token(
        {"order": "asc", "max_items": "20", "is_outlined": "False"},
        {"cursor": "c"},
    )

    with pytest.raises(database.InvalidNextTokenException):
        await db.get_repeating_queue_page(
            is_outlined=True,
            params=pagination.PageParams(next_token=token),
        )

    fetch_page.assert_not_awaited()
