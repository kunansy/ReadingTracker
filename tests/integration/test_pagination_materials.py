"""Keyset pagination of materials, reading logs, cards, the repeating queue and the estimate."""

import datetime
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest

from tests.integration import factories, helpers, helpers_materials as h
from tracker.cards import db as cards_db
from tracker.common import database, pagination
from tracker.common.pagination import Order, Page, PageParams
from tracker.materials import db as materials_db
from tracker.models import enums, models
from tracker.reading_log import db as logs_db


PAGE_SIZE = 3
ago = factories.days_ago


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> h.Clock:
    return h.freeze_clock(monkeypatch)


@dataclass(frozen=True)
class Listing:
    fetch: Callable[[PageParams], Awaitable[Page[Any]]]
    # ids in ascending listing order
    seed: Callable[[h.Clock, int], Awaitable[list[UUID]]]
    # sorts after every seeded row
    add_last: Callable[[h.Clock], Awaitable[UUID]]
    get_id: Callable[[Any], UUID]
    default_order: Order


async def seed_cards(clock: h.Clock, count: int) -> list[UUID]:
    material_id = await h.queued(clock)
    note_id = await factories.insert_note(material_id=material_id)
    card_ids = []
    for number in range(count):
        clock.tick()
        card_ids.append(
            await cards_db.add_card(
                material_id=material_id,
                note_id=note_id,
                question=f"Question {number}",
            ),
        )
    return card_ids


async def add_last_card(clock: h.Clock) -> UUID:
    [card_id] = await seed_cards(clock, 1)
    return card_id


async def seed_logs(clock: h.Clock, count: int) -> list[UUID]:
    """Logs of two materials; each date is shared by both, so the sort key breaks the tie."""
    materials = [await h.reading(clock, started=ago(90)) for _ in range(2)]
    for number in range(count):
        await logs_db.insert_log_record(
            material_id=materials[number % 2],
            count=number + 1,
            date=ago(60 - number // 2),
        )
    rows = await helpers.fetch_table(
        models.ReadingLog,
        models.ReadingLog.c.date,
        models.ReadingLog.c.sort_key,
    )
    return [row["log_id"] for row in rows]


async def add_last_log(clock: h.Clock) -> UUID:
    material_id = await h.reading(clock, started=ago(90))
    return await logs_db.insert_log_record(material_id=material_id, count=1, date=ago(0))


async def seed_completed(clock: h.Clock, count: int) -> list[UUID]:
    """Completion dates are shared by pairs of materials, so the sort key breaks the tie."""
    return [
        await h.completed(clock, started=ago(300), finished=ago(200 - number // 2))
        for number in range(count)
    ]


async def add_last_completed(clock: h.Clock) -> UUID:
    return await h.completed(clock, started=ago(300), finished=ago(100))


async def seed_reading(clock: h.Clock, count: int) -> list[UUID]:
    return [
        await h.reading(clock, started=ago(200 - number // 2)) for number in range(count)
    ]


async def add_last_reading(clock: h.Clock) -> UUID:
    return await h.reading(clock, started=ago(0))


async def seed_queue(clock: h.Clock, count: int) -> list[UUID]:
    return [await h.queued(clock, pages=number + 1) for number in range(count)]


async def add_last_queued(clock: h.Clock) -> UUID:
    return await h.queued(clock)


LISTINGS = {
    "cards": Listing(
        fetch=lambda params: cards_db.get_cards_page(material_id=None, params=params),
        seed=seed_cards,
        add_last=add_last_card,
        get_id=lambda card: card.card_id,
        default_order=Order.DESC,
    ),
    "reading logs": Listing(
        fetch=lambda params: logs_db.list_log_records_page(
            material_id=None, params=params
        ),
        seed=seed_logs,
        add_last=add_last_log,
        get_id=lambda log: log.log_id,
        default_order=Order.DESC,
    ),
    "completed materials": Listing(
        fetch=lambda params: materials_db.completed_statistics_page(params=params),
        seed=seed_completed,
        add_last=add_last_completed,
        get_id=lambda stat: stat.material.material_id,
        default_order=Order.DESC,
    ),
    "reading materials": Listing(
        fetch=lambda params: materials_db.reading_statistics_page(params=params),
        seed=seed_reading,
        add_last=add_last_reading,
        get_id=lambda stat: stat.material.material_id,
        default_order=Order.DESC,
    ),
    "repeating queue": Listing(
        fetch=lambda params: materials_db.get_repeating_queue_page(
            is_outlined=False,
            params=params,
        ),
        seed=seed_completed,
        add_last=add_last_completed,
        get_id=lambda item: item.material_id,
        default_order=Order.ASC,
    ),
    "estimate": Listing(
        fetch=lambda params: materials_db.estimate_page(start_date=ago(0), params=params),
        seed=seed_queue,
        add_last=add_last_queued,
        get_id=lambda estimate: estimate.material.material_id,
        default_order=Order.DESC,
    ),
}

every_listing = pytest.mark.parametrize("listing", LISTINGS.values(), ids=LISTINGS.keys())
# listings whose cursor is parsed into the values of several columns
KEYSET_LISTINGS = ("reading logs", "completed materials", "reading materials")
string_cursor_listing = pytest.mark.parametrize(
    "listing",
    [LISTINGS[name] for name in LISTINGS if name not in KEYSET_LISTINGS],
    ids=[name for name in LISTINGS if name not in KEYSET_LISTINGS],
)
keyset_listing = pytest.mark.parametrize(
    "listing",
    [LISTINGS[name] for name in KEYSET_LISTINGS],
    ids=KEYSET_LISTINGS,
)
both_orders = pytest.mark.parametrize("order", list(Order), ids=lambda order: order.value)


def in_order(ids: list[UUID], order: Order) -> list[UUID]:
    return ids if order == Order.ASC else ids[::-1]


def page_ids(listing: Listing, pages: list[Page[Any]]) -> list[list[UUID]]:
    return [[listing.get_id(item) for item in page.items] for page in pages]


@every_listing
@both_orders
@pytest.mark.parametrize(
    ("rows", "expected_page_sizes"),
    [
        (0, [0]),
        (1, [1]),
        (PAGE_SIZE, [3]),
        (PAGE_SIZE + 1, [3, 1]),
        (2 * PAGE_SIZE, [3, 3]),
        (2 * PAGE_SIZE + 1, [3, 3, 1]),
    ],
    ids=[
        "no rows",
        "one row",
        "page size",
        "page size + 1",
        "two pages",
        "two pages + 1",
    ],
)
async def test_walk_lists_every_row_once(
    clock, listing, order, rows, expected_page_sizes
):
    ids = await listing.seed(clock, rows)

    pages = await helpers.walk_pages(listing.fetch, page_size=PAGE_SIZE, order=order)

    listed = page_ids(listing, pages)
    assert [len(page) for page in listed] == expected_page_sizes
    assert [item for page in listed for item in page] == in_order(ids, order)
    assert [page.total_count for page in pages] == [rows] * len(pages)
    assert [page.next_token is None for page in pages] == [False] * (len(pages) - 1) + [
        True
    ]


@every_listing
async def test_default_order(clock, listing):
    ids = await listing.seed(clock, 4)

    pages = await helpers.walk_pages(listing.fetch, page_size=PAGE_SIZE)

    listed = [item for page in page_ids(listing, pages) for item in page]
    assert listed == in_order(ids, listing.default_order)


@every_listing
@pytest.mark.parametrize("page_size", [1, pagination.MAX_PAGE_SIZE], ids=["one", "max"])
async def test_walk_with_the_smallest_and_the_largest_page(clock, listing, page_size):
    ids = await listing.seed(clock, 4)

    pages = await helpers.walk_pages(listing.fetch, page_size=page_size, order=Order.ASC)

    listed = [item for page in page_ids(listing, pages) for item in page]
    assert listed == ids
    assert len(pages) == (4 if page_size == 1 else 1)


@every_listing
@both_orders
async def test_row_added_between_two_pages_neither_repeats_nor_skips_listed_rows(
    clock,
    listing,
    order,
):
    ids = await listing.seed(clock, 5)
    first = await listing.fetch(PageParams(page_size=2, order=order))

    added_id = await listing.add_last(clock)
    rest = await helpers.walk_pages(
        lambda params: listing.fetch(
            params.model_copy(
                update={"next_token": params.next_token or first.next_token}
            ),
        ),
        page_size=2,
        order=order,
    )

    listed = [item for page in page_ids(listing, [first, *rest]) for item in page]
    # the new row sorts last: an ascending walk reaches it, a descending one has passed it
    assert listed == (ids + [added_id] if order == Order.ASC else ids[::-1])


async def test_reading_material_logged_between_two_pages_is_not_skipped(clock):
    listing = LISTINGS["reading materials"]
    ids = await listing.seed(clock, 3)
    first = await listing.fetch(PageParams(page_size=1))

    await logs_db.insert_log_record(material_id=ids[0], count=1, date=ago(0))
    rest = await helpers.walk_pages(
        lambda params: listing.fetch(
            params.model_copy(
                update={"next_token": params.next_token or first.next_token}
            ),
        ),
        page_size=1,
    )

    listed = [item for page in page_ids(listing, [first, *rest]) for item in page]
    assert sorted(listed) == sorted(ids)


def card_cursor(row: dict[str, Any]) -> str:
    return row["sort_key"]


def log_cursor(row: dict[str, Any]) -> str:
    return f"{row['date'].isoformat()}$${row['sort_key']}"


def completed_cursor(row: dict[str, Any]) -> str:
    return f"{row['completed_at'].isoformat()}.000000$${row['sort_key']}"


def started_cursor(row: dict[str, Any]) -> str:
    return f"{row['started_at'].isoformat()}.000000$${row['sort_key']}"


def repeat_cursor(row: dict[str, Any]) -> str:
    return f"{row['completed_at'].date().isoformat()}$${row['sort_key']}"


@pytest.mark.parametrize(
    ("name", "table", "cursor_of", "params"),
    [
        ("cards", models.Cards, card_cursor, {"material_id": ""}),
        ("reading logs", models.ReadingLog, log_cursor, {"material_id": ""}),
        (
            "completed materials",
            models.Materials,
            completed_cursor,
            {"material_type": "", "is_outlined": "", "tags": ""},
        ),
        ("reading materials", models.Materials, started_cursor, {}),
        ("repeating queue", models.Materials, repeat_cursor, {"is_outlined": "False"}),
    ],
    ids=lambda value: value if isinstance(value, str) else "",
)
async def test_token_holds_the_request_and_the_first_row_of_the_next_page(
    clock,
    name,
    table,
    cursor_of,
    params,
):
    listing = LISTINGS[name]
    ids = await listing.seed(clock, 3)
    primary_key = next(iter(table.primary_key.columns)).name
    rows = {row[primary_key]: row for row in await helpers.fetch_table(table)}

    page = await listing.fetch(PageParams(page_size=2, order=Order.ASC))

    assert helpers.decode_token(page.next_token) == {
        "params": {"order": "asc", "max_items": "2"} | params,
        "continue_from": {"cursor": cursor_of(rows[ids[2]])},
    }


async def test_estimate_token_also_holds_the_start_date_of_the_next_page(clock):
    ids = await seed_queue(clock, 3)
    third = await factories.fetch_row(models.Materials, ids[2])

    page = await materials_db.estimate_page(
        start_date=datetime.date(2024, 4, 1),
        params=PageParams(page_size=2, order=Order.ASC),
    )

    # 1 and 2 pages at one page a day: 2024-04-01..02 and 2024-04-03..05
    assert helpers.decode_token(page.next_token) == {
        "params": {"order": "asc", "max_items": "2"},
        "continue_from": {"cursor": third["sort_key"], "start_date": "2024-04-06"},
    }


BAD_TOKENS: dict[str, Callable[[dict[str, Any]], str]] = {
    "not base64": lambda _: "%%%",
    "not json": lambda _: "aGVsbG8=",
    "json list": lambda _: helpers.encode_token([]),
    "no continue_from": lambda payload: helpers.encode_token({"params": payload["params"]}),
    "no params": lambda payload: helpers.encode_token(
        {"continue_from": payload["continue_from"]},
    ),
    "extra key": lambda payload: helpers.encode_token(payload | {"version": "1"}),
    "no cursor": lambda payload: helpers.encode_token(payload | {"continue_from": {}}),
    "cursor is a number": lambda payload: helpers.encode_token(
        payload | {"continue_from": payload["continue_from"] | {"cursor": 1}},
    ),
    "NUL in the cursor": lambda payload: helpers.encode_token(
        payload | {"continue_from": payload["continue_from"] | {"cursor": "a\x00b"}},
    ),
    "params are a list": lambda payload: helpers.encode_token(payload | {"params": []}),
    "another page size": lambda payload: helpers.encode_token(
        payload | {"params": payload["params"] | {"max_items": "2"}},
    ),
    "another order": lambda payload: helpers.encode_token(
        payload | {"params": payload["params"] | {"order": "sideways"}},
    ),
    "extra filter": lambda payload: helpers.encode_token(
        payload | {"params": payload["params"] | {"owner": "someone"}},
    ),
}


@every_listing
@pytest.mark.parametrize("make_token", BAD_TOKENS.values(), ids=BAD_TOKENS.keys())
async def test_tampered_token_is_rejected(clock, listing, make_token):
    await listing.seed(clock, 2)
    first = await listing.fetch(PageParams(page_size=1))
    token = make_token(helpers.decode_token(first.next_token))

    with pytest.raises(database.InvalidNextTokenException):
        await listing.fetch(PageParams(page_size=1, next_token=token))


@every_listing
@pytest.mark.parametrize(
    "changed",
    [{"page_size": 2}, {"order": "other"}],
    ids=["page size", "order"],
)
async def test_token_is_rejected_with_changed_page_params(clock, listing, changed):
    await listing.seed(clock, 2)
    first = await listing.fetch(PageParams(page_size=1))
    if "order" in changed:
        other = Order.ASC if listing.default_order == Order.DESC else Order.DESC
        changed = {"order": other}
    params = PageParams(page_size=1, next_token=first.next_token).model_copy(
        update=changed
    )

    with pytest.raises(database.InvalidNextTokenException, match="^Invalid nextToken$"):
        await listing.fetch(params)


@every_listing
async def test_token_is_accepted_with_the_default_order_given_explicitly(clock, listing):
    ids = await listing.seed(clock, 2)
    first = await listing.fetch(PageParams(page_size=1))

    second = await listing.fetch(
        PageParams(page_size=1, next_token=first.next_token, order=listing.default_order),
    )

    assert page_ids(listing, [first, second]) == [
        [item] for item in in_order(ids, listing.default_order)
    ]


FORGED_CURSORS = pytest.mark.parametrize(
    "cursor", ["", "~", "0", "$$", "'; DROP TABLE materials; --"]
)


@string_cursor_listing
@FORGED_CURSORS
async def test_forged_cursor_gives_a_page_of_seeded_rows(clock, listing, cursor):
    ids = await listing.seed(clock, 2)
    first = await listing.fetch(PageParams(page_size=1))

    page = await listing.fetch(
        PageParams(page_size=1, next_token=helpers.with_cursor(first.next_token, cursor)),
    )

    assert len(page.items) <= 1
    assert set(page_ids(listing, [page])[0]) <= set(ids)
    assert await factories.count_rows(models.Materials) > 0


@keyset_listing
@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "~",
        "0",
        "$$",
        "'; DROP TABLE materials; --",
        "2024-13-01$$key",
        "2024-01-01T25:00:00.000000$$key",
        "2024-01-01T00:00:00.000000+05:00$$key",
        "2024-01-01T00:00:00.000000Z$$key",
    ],
)
async def test_forged_cursor_of_a_keyset_listing_is_rejected(clock, listing, cursor):
    await listing.seed(clock, 2)
    first = await listing.fetch(PageParams(page_size=1))

    with pytest.raises(database.InvalidNextTokenException, match="^Invalid nextToken$"):
        await listing.fetch(
            PageParams(page_size=1, next_token=helpers.with_cursor(first.next_token, cursor)),
        )


LAST_CURSOR = {"date": "9999-12-31$$~", "datetime": "9999-12-31T23:59:59.999999$$~"}
FIRST_CURSOR = {"date": "0001-01-01$$", "datetime": "0001-01-01T00:00:00.000000$$"}


def _cursor_kind(token: str) -> str:
    cursor = helpers.decode_token(token)["continue_from"]["cursor"]
    return "datetime" if "T" in cursor.split("$$", 1)[0] else "date"


@keyset_listing
@pytest.mark.parametrize(
    ("bound", "order", "is_empty"),
    [
        (LAST_CURSOR, Order.ASC, True),
        (LAST_CURSOR, Order.DESC, False),
        (FIRST_CURSOR, Order.ASC, False),
        (FIRST_CURSOR, Order.DESC, True),
    ],
    ids=["asc-past-the-end", "desc-from-the-end", "asc-from-the-start", "desc-past-the-start"],
)
async def test_forged_but_well_formed_keyset_cursor_gives_a_consistent_page(
    clock, listing, bound, order, is_empty
):
    ids = await listing.seed(clock, 2)
    first = await listing.fetch(PageParams(page_size=1, order=order))
    cursor = bound[_cursor_kind(first.next_token)]

    page = await listing.fetch(
        PageParams(
            page_size=1,
            order=order,
            next_token=helpers.with_cursor(first.next_token, cursor),
        ),
    )

    expected = [] if is_empty else in_order(ids, order)[:1]
    assert page_ids(listing, [page]) == [expected]


async def test_cursor_past_the_end_gives_an_empty_last_page(clock):
    await seed_cards(clock, 2)
    first = await cards_db.get_cards_page(
        material_id=None,
        params=PageParams(page_size=1, order=Order.ASC),
    )

    page = await cards_db.get_cards_page(
        material_id=None,
        params=PageParams(
            page_size=1,
            order=Order.ASC,
            next_token=helpers.with_cursor(first.next_token, "~"),
        ),
    )

    assert (page.items, page.next_token, page.total_count) == ([], None, 2)


async def test_logs_listing_rejects_a_token_of_the_cards_listing(clock):
    await seed_cards(clock, 2)
    await seed_logs(clock, 2)
    cards_page = await cards_db.get_cards_page(
        material_id=None, params=PageParams(page_size=1)
    )

    # both listings bind the same params (order, max_items, material_id): only the cursor
    # of a card, which is not a date, tells the token apart
    with pytest.raises(database.InvalidNextTokenException, match="^Invalid nextToken$"):
        await logs_db.list_log_records_page(
            material_id=None,
            params=PageParams(page_size=1, next_token=cards_page.next_token),
        )


async def test_cards_page_walks_only_the_cards_of_the_material(clock):
    await seed_cards(clock, 2)
    ids = await seed_cards(clock, 4)
    material_id = (await factories.fetch_row(models.Cards, ids[0]))["material_id"]

    pages = await helpers.walk_pages(
        lambda params: cards_db.get_cards_page(material_id=material_id, params=params),
        page_size=PAGE_SIZE,
    )

    assert [[card.card_id for card in page.items] for page in pages] == [
        ids[:0:-1],
        ids[:1],
    ]
    assert [page.total_count for page in pages] == [4, 4]


async def test_cards_token_is_rejected_for_another_material(clock):
    await seed_cards(clock, 2)
    first = await cards_db.get_cards_page(
        material_id=None, params=PageParams(page_size=1)
    )

    with pytest.raises(database.InvalidNextTokenException, match="^Invalid nextToken$"):
        await cards_db.get_cards_page(
            material_id=h.MISSING_ID,
            params=PageParams(page_size=1, next_token=first.next_token),
        )


async def test_logs_page_walks_only_the_logs_of_the_material(clock):
    await seed_logs(clock, 8)
    logs = await logs_db.list_log_records()
    material_id = logs[0].material_id
    expected = [log.log_id for log in logs if log.material_id == material_id]

    pages = await helpers.walk_pages(
        lambda params: logs_db.list_log_records_page(
            material_id=material_id, params=params
        ),
        page_size=PAGE_SIZE,
    )

    assert [[log.log_id for log in page.items] for page in pages] == [
        expected[:3],
        expected[3:],
    ]
    assert len(expected) == 4
    assert [page.total_count for page in pages] == [4, 4]


async def test_logs_token_is_rejected_for_another_material(clock):
    await seed_logs(clock, 2)
    first = await logs_db.list_log_records_page(
        material_id=None,
        params=PageParams(page_size=1),
    )

    with pytest.raises(database.InvalidNextTokenException, match="^Invalid nextToken$"):
        await logs_db.list_log_records_page(
            material_id=h.MISSING_ID,
            params=PageParams(page_size=1, next_token=first.next_token),
        )


async def test_completed_page_walks_only_the_filtered_materials(clock):
    book = enums.MaterialTypesEnum.book
    article = enums.MaterialTypesEnum.article
    matching = []
    for number in range(4):
        await h.completed(
            clock,
            started=ago(300),
            finished=ago(200 - number),
            material_type=article,
            tags="keyset, paging",
        )
        await h.completed(
            clock, started=ago(300), finished=ago(200 - number), tags="keyset"
        )
        material_id = await h.completed(
            clock,
            started=ago(300),
            finished=ago(200 - number),
            tags="keyset, paging",
        )
        await materials_db.outline_material(material_id=material_id)
        matching.append(material_id)

    pages = await helpers.walk_pages(
        lambda params: materials_db.completed_statistics_page(
            material_type=book,
            is_outlined=True,
            tags={"paging", "keyset"},
            params=params,
        ),
        page_size=PAGE_SIZE,
        order=Order.ASC,
    )

    assert [[stat.material.material_id for stat in page.items] for page in pages] == [
        matching[:3],
        matching[3:],
    ]
    assert [page.total_count for page in pages] == [4, 4]
    assert helpers.decode_token(pages[0].next_token)["params"] == {
        "order": "asc",
        "max_items": "3",
        "material_type": "book",
        "is_outlined": "True",
        "tags": "keyset,paging",
    }


@pytest.mark.parametrize(
    "changed",
    [
        {"material_type": enums.MaterialTypesEnum.article},
        {"is_outlined": True},
        {"is_outlined": False},
        {"tags": {"keyset"}},
    ],
    ids=["material type", "outlined", "not outlined", "tags"],
)
async def test_completed_token_is_rejected_with_a_changed_filter(clock, changed):
    await seed_completed(clock, 2)
    first = await materials_db.completed_statistics_page(params=PageParams(page_size=1))

    with pytest.raises(database.InvalidNextTokenException, match="^Invalid nextToken$"):
        await materials_db.completed_statistics_page(
            **changed,
            params=PageParams(page_size=1, next_token=first.next_token),
        )


async def test_repeating_queue_page_walks_only_outlined_materials(clock):
    outlined = []
    for number in range(4):
        await h.completed(clock, started=ago(300), finished=ago(200 - number))
        material_id = await h.completed(
            clock, started=ago(300), finished=ago(200 - number)
        )
        await materials_db.outline_material(material_id=material_id)
        await factories.insert_note(material_id=material_id)
        outlined.append(material_id)

    pages = await helpers.walk_pages(
        lambda params: materials_db.get_repeating_queue_page(
            is_outlined=True, params=params
        ),
        page_size=PAGE_SIZE,
    )

    assert [[item.material_id for item in page.items] for page in pages] == [
        outlined[:3],
        outlined[3:],
    ]
    assert [page.total_count for page in pages] == [4, 4]


async def test_repeating_queue_token_is_rejected_with_a_changed_filter(clock):
    await seed_completed(clock, 2)
    first = await materials_db.get_repeating_queue_page(
        is_outlined=False,
        params=PageParams(page_size=1),
    )

    with pytest.raises(database.InvalidNextTokenException, match="^Invalid nextToken$"):
        await materials_db.get_repeating_queue_page(
            is_outlined=True,
            params=PageParams(page_size=1, next_token=first.next_token),
        )


async def test_repeating_queue_follows_the_repeat_date_not_the_completion_date(clock):
    repeated = await h.completed(clock, started=ago(400), finished=ago(300))
    plain = await h.completed(clock, started=ago(400), finished=ago(200))
    at = datetime.datetime.combine(ago(100), datetime.time(9))
    await h.repeat(clock, repeated, at=at)

    pages = await helpers.walk_pages(
        lambda params: materials_db.get_repeating_queue_page(
            is_outlined=False, params=params
        ),
        page_size=1,
    )

    # to repeat at: 200 days ago for the plain one, 100 - 30 days ago for the repeated one
    assert [[item.material_id for item in page.items] for page in pages] == [
        [plain],
        [repeated],
    ]


def estimates(page: Page[materials_db.MaterialEstimate]) -> list[tuple[Any, ...]]:
    return [
        (
            e.material.material_id,
            e.will_be_started,
            e.will_be_completed,
            e.expected_duration,
        )
        for e in page.items
    ]


@both_orders
async def test_estimate_pages_continue_the_dates_of_the_previous_page(clock, order):
    await seed_queue(clock, 5)
    start = datetime.date(2024, 4, 1)

    async def fetch(params: PageParams) -> Page[materials_db.MaterialEstimate]:
        return await materials_db.estimate_page(start_date=start, params=params)

    whole = await fetch(PageParams(page_size=100, order=order))
    pages = await helpers.walk_pages(fetch, page_size=2, order=order)

    assert [item for page in pages for item in estimates(page)] == estimates(whole)
    assert whole.items[0].will_be_started == start
    # 1..5 pages at one page a day, both ends included: 2 + 3 + 4 + 5 + 6 days
    assert whole.items[-1].will_be_completed == datetime.date(2024, 4, 20)


async def test_estimate_ignores_the_start_date_of_a_later_request_current_behaviour(
    clock,
):
    await seed_queue(clock, 2)
    first = await materials_db.estimate_page(
        start_date=datetime.date(2024, 4, 1),
        params=PageParams(page_size=1, order=Order.ASC),
    )

    second = await materials_db.estimate_page(
        start_date=datetime.date(2030, 1, 1),
        params=PageParams(page_size=1, order=Order.ASC, next_token=first.next_token),
    )

    assert second.items[0].will_be_started == datetime.date(2024, 4, 3)


@pytest.mark.parametrize(
    "continue_from",
    [{}, {"start_date": "not-a-date"}, {"start_date": ""}, {"start_date": "2024-02-30"}],
    ids=["missing", "not a date", "empty", "impossible date"],
)
async def test_estimate_token_without_a_valid_start_date_is_rejected(
    clock, continue_from
):
    await seed_queue(clock, 2)
    first = await materials_db.estimate_page(
        start_date=ago(0), params=PageParams(page_size=1)
    )
    payload = helpers.decode_token(first.next_token)
    cursor = {"cursor": payload["continue_from"]["cursor"]}
    token = helpers.encode_token(payload | {"continue_from": cursor | continue_from})

    with pytest.raises(database.InvalidNextTokenException, match="^Invalid nextToken$"):
        await materials_db.estimate_page(
            start_date=ago(0),
            params=PageParams(page_size=1, next_token=token),
        )


@pytest.mark.parametrize(
    ("name", "index"),
    [("cards", "cards_sort_key_key"), ("estimate", "materials_sort_key_key")],
)
@both_orders
async def test_page_is_read_from_the_sort_key_index_without_sorting(
    clock,
    mocker,
    name,
    index,
    order,
):
    listing = LISTINGS[name]
    await listing.seed(clock, 4)
    paginate = mocker.spy(pagination, "paginate")

    first = await listing.fetch(PageParams(page_size=2, order=order))
    first_plan = await helpers.explain(paginate.spy_return)
    await listing.fetch(PageParams(page_size=2, order=order, next_token=first.next_token))
    next_plan = await helpers.explain(paginate.spy_return)

    for plan in (first_plan, next_plan):
        assert index in plan
        assert "Sort" not in plan
    # the cursor is an index condition, not a filter over the whole index
    assert re.search(r"Index Cond: \(\(?(\w+\.)?sort_key\)?(::text)? [<>]=", next_plan), (
        next_plan
    )


@pytest.mark.parametrize(
    ("name", "index"),
    [
        ("reading logs", "ix_reading_log_date_sort_key"),
        ("completed materials", "ix_materials_completed_at_sort_key"),
        ("reading materials", "ix_materials_started_at_sort_key"),
    ],
)
@both_orders
async def test_keyset_page_is_read_from_its_index_without_sorting(
    clock,
    mocker,
    name,
    index,
    order,
):
    listing = LISTINGS[name]
    await listing.seed(clock, 4)
    paginate = mocker.spy(pagination, "paginate")

    first = await listing.fetch(PageParams(page_size=2, order=order))
    first_plan = await helpers.explain(paginate.spy_return)
    await listing.fetch(PageParams(page_size=2, order=order, next_token=first.next_token))
    next_plan = await helpers.explain(paginate.spy_return)

    for plan in (first_plan, next_plan):
        assert index in plan, plan
        assert "Sort" not in plan, plan
    # the row value of the cursor is an index condition, not a filter
    assert re.search(r"Index Cond: .*ROW\(\w+, \(sort_key\)::text\) [<>]= ROW\(", next_plan), (
        next_plan
    )


async def test_repeating_queue_page_sorts_the_whole_listing_current_behaviour(clock, mocker):
    """The queue is ordered by a computed repeat date, which no index can cover."""
    name = "repeating queue"
    listing = LISTINGS[name]
    await listing.seed(clock, 4)
    paginate = mocker.spy(pagination, "paginate")

    first = await listing.fetch(PageParams(page_size=2))
    await listing.fetch(PageParams(page_size=2, next_token=first.next_token))
    plan = await helpers.explain(paginate.spy_return)

    assert "Sort Key" in plan
    assert "sort_key_key" not in plan
