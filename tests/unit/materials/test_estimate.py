import base64
import datetime
import json
from decimal import Decimal

import pytest

from tests.unit.materials.helpers import compile_sql, make_material, uid
from tracker.common import database, pagination
from tracker.materials import db
from tracker.models import enums


START = datetime.date(2024, 3, 10)
BOOK = enums.MaterialTypesEnum.book
ARTICLE = enums.MaterialTypesEnum.article


def _decode(token: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(token))


@pytest.fixture
def fetch_rows(mocker):
    return mocker.patch.object(
        pagination,
        "fetch_rows",
        mocker.AsyncMock(return_value=([], None, 0)),
    )


@pytest.fixture
def means(mocker):
    return mocker.patch.object(
        db,
        "get_means",
        mocker.AsyncMock(return_value={BOOK: Decimal(20)}),
    )


async def test_estimates_follow_one_another_from_the_start_date(fetch_rows, means):
    book = make_material(material_id=uid(1), pages=100, material_type=BOOK)
    article = make_material(material_id=uid(2), pages=10, material_type=ARTICLE)
    fetch_rows.return_value = ([book, article], None, 2)

    page = await db.estimate_page(start_date=START, params=pagination.PageParams())

    assert page.items == [
        db.MaterialEstimate(
            material=book,
            will_be_started=START,
            will_be_completed=datetime.date(2024, 3, 15),
            expected_duration=6,
        ),
        # no mean for articles: one page a day
        db.MaterialEstimate(
            material=article,
            will_be_started=datetime.date(2024, 3, 16),
            will_be_completed=datetime.date(2024, 3, 26),
            expected_duration=11,
        ),
    ]
    assert page.total_count == 2
    assert page.next_token is None


async def test_queue_is_read_in_sort_key_order_by_default_desc(fetch_rows, means):
    material = make_material()

    await db.estimate_page(start_date=START, params=pagination.PageParams(page_size=7))

    stmt = fetch_rows.await_args.args[0]
    kwargs = fetch_rows.await_args.kwargs
    assert compile_sql(stmt).endswith(
        "FROM materials WHERE materials.started_at IS NULL ORDER BY materials.sort_key",
    )
    assert compile_sql(kwargs["cursor_expr"]) == 'materials.sort_key COLLATE "C"'
    assert kwargs["request"].order == pagination.Order.DESC
    assert kwargs["request"].params == {"order": "desc", "max_items": "7"}
    assert kwargs["request"].cursor is None
    assert kwargs["to_item"](material) == material


async def test_empty_queue_gives_empty_page_without_token(fetch_rows, means):
    page = await db.estimate_page(start_date=START, params=pagination.PageParams())

    assert page == pagination.Page(items=[], next_token=None, total_count=0)


@pytest.mark.parametrize(
    ("pages", "mean", "expected_end", "expected_duration"),
    [
        (0, Decimal(20), START, 1),
        (1, Decimal(20), START, 1),
        (10, Decimal(20), START, 1),
        (11, Decimal(20), datetime.date(2024, 3, 11), 2),
        (20, Decimal(20), datetime.date(2024, 3, 11), 2),
        (30, Decimal(20), datetime.date(2024, 3, 12), 3),
        (100, Decimal("33.33"), datetime.date(2024, 3, 13), 4),
        (366, Decimal(1), datetime.date(2025, 3, 11), 367),
    ],
    ids=[
        "zero-pages",
        "one-page",
        "half-rounds-to-even-down",
        "just-over-half",
        "exactly-one-day",
        "half-rounds-to-even-up",
        "fractional-mean",
        "crosses-year",
    ],
)
async def test_expected_duration_is_rounded_days_plus_the_start_day(
    fetch_rows,
    means,
    pages,
    mean,
    expected_end,
    expected_duration,
):
    means.return_value = {BOOK: mean}
    fetch_rows.return_value = ([make_material(pages=pages)], None, 1)

    page = await db.estimate_page(start_date=START, params=pagination.PageParams())

    [estimate] = page.items
    assert estimate.will_be_started == START
    assert estimate.will_be_completed == expected_end
    assert estimate.expected_duration == expected_duration


async def test_next_token_carries_cursor_and_the_next_start_date(fetch_rows, means):
    fetch_rows.return_value = ([make_material(pages=100)], "next-cursor", 5)

    page = await db.estimate_page(start_date=START, params=pagination.PageParams(page_size=1))

    assert page.total_count == 5
    assert _decode(page.next_token) == {
        "params": {"order": "desc", "max_items": "1"},
        "continue_from": {"cursor": "next-cursor", "start_date": "2024-03-16"},
    }


async def test_next_page_continues_from_the_date_in_the_token(fetch_rows, means):
    token = pagination.encode_next_token(
        {"order": "desc", "max_items": "20"},
        {"cursor": "next-cursor", "start_date": "2024-03-16"},
    )
    fetch_rows.return_value = ([make_material(pages=40)], None, 5)

    page = await db.estimate_page(
        start_date=datetime.date(1999, 1, 1),
        params=pagination.PageParams(next_token=token),
    )

    [estimate] = page.items
    assert estimate.will_be_started == datetime.date(2024, 3, 16)
    assert estimate.will_be_completed == datetime.date(2024, 3, 18)
    assert fetch_rows.await_args.kwargs["request"].cursor == "next-cursor"


@pytest.mark.parametrize(
    "continue_from",
    [{"cursor": "c"}, {"cursor": "c", "start_date": "not-a-date"}],
    ids=["no-start-date", "bad-start-date"],
)
async def test_token_without_valid_start_date_is_rejected(fetch_rows, means, continue_from):
    token = pagination.encode_next_token(
        {"order": "desc", "max_items": "20"},
        continue_from,
    )

    with pytest.raises(database.InvalidNextTokenException, match="no valid start date"):
        await db.estimate_page(
            start_date=START,
            params=pagination.PageParams(next_token=token),
        )

    fetch_rows.assert_not_awaited()


async def test_token_of_another_page_size_is_rejected(fetch_rows, means):
    token = pagination.encode_next_token(
        {"order": "desc", "max_items": "20"},
        {"cursor": "c", "start_date": "2024-03-16"},
    )

    with pytest.raises(database.InvalidNextTokenException):
        await db.estimate_page(
            start_date=START,
            params=pagination.PageParams(next_token=token, page_size=21),
        )

    fetch_rows.assert_not_awaited()


async def test_zero_mean_divides_by_zero_current_behaviour(fetch_rows, means):
    means.return_value = {BOOK: Decimal(0)}
    fetch_rows.return_value = ([make_material(pages=100)], None, 1)

    with pytest.raises(ZeroDivisionError):
        await db.estimate_page(start_date=START, params=pagination.PageParams())
