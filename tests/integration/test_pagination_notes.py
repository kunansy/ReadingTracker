"""Keyset pagination of the two paginated reads in tracker/notes/db.py."""

import re
import uuid
from collections.abc import Awaitable, Callable

import pytest

from tests.integration import factories, helpers
from tracker.common import database
from tracker.common.pagination import Order, Page, PageParams
from tracker.models import models
from tracker.notes import db as notes_db


type Fetch = Callable[[PageParams], Awaitable[Page[notes_db.Note]]]

PAGE_SIZE = 3


def _search(**filters) -> Fetch:
    kwargs = {
        "material_id": None,
        "query": None,
        "tags": set(),
        "note_ids": None,
        **filters,
    }

    async def fetch(params: PageParams) -> Page[notes_db.Note]:
        return await notes_db.search_notes_page(**kwargs, params=params)

    return fetch


def _links(note_id: uuid.UUID | str) -> Fetch:
    async def fetch(params: PageParams) -> Page[notes_db.Note]:
        return await notes_db.get_links_from_page(note_id=note_id, params=params)

    return fetch


def _ids(pages: list[Page[notes_db.Note]]) -> list[uuid.UUID]:
    return [note.note_id for note in helpers.page_items(pages)]


async def _sort_key(note_id: uuid.UUID) -> str:
    row = await factories.fetch_row(models.Notes, note_id)
    assert row is not None
    return row["sort_key"]


async def _insert_search_notes(count: int) -> list[uuid.UUID]:
    """Notes of one material, returned in listing order (by page)."""
    material_id = await factories.insert_material()
    # inserted in reverse so the listing order differs from the insertion order
    ids = [
        await factories.insert_note(material_id=material_id, page=page)
        for page in range(count, 0, -1)
    ]
    return ids[::-1]


async def _insert_links(count: int) -> tuple[uuid.UUID, list[uuid.UUID]]:
    """A target note and `count` notes linking to it, in listing order (by note_number)."""
    material_id = await factories.insert_material()
    target = await factories.insert_note(material_id=material_id)
    links = [
        # descending pages: the order by note_number is the reverse of the order by sort_key
        await factories.insert_note(
            material_id=material_id,
            link_id=target,
            page=count - index,
        )
        for index in range(count)
    ]
    return target, links


LISTINGS = ["search", "links"]


async def _listing(name: str, count: int) -> tuple[Fetch, list[uuid.UUID]]:
    if name == "search":
        ids = await _insert_search_notes(count)
        return _search(), ids

    target, ids = await _insert_links(count)
    return _links(target), ids


@pytest.mark.parametrize("name", LISTINGS)
async def test_exactly_page_size_rows_fit_one_page_without_a_token(name):
    fetch, ids = await _listing(name, PAGE_SIZE)

    page = await fetch(PageParams(page_size=PAGE_SIZE))

    assert [note.note_id for note in page.items] == ids
    assert page.next_token is None
    assert page.total_count == PAGE_SIZE


@pytest.mark.parametrize("name", LISTINGS)
async def test_page_size_plus_one_rows_give_a_token_and_a_last_page_of_one(name):
    fetch, ids = await _listing(name, PAGE_SIZE + 1)

    first = await fetch(PageParams(page_size=PAGE_SIZE))
    second = await fetch(PageParams(page_size=PAGE_SIZE, next_token=first.next_token))

    assert [note.note_id for note in first.items] == ids[:PAGE_SIZE]
    assert first.next_token is not None
    assert [note.note_id for note in second.items] == ids[PAGE_SIZE:]
    assert second.next_token is None
    assert first.total_count == second.total_count == PAGE_SIZE + 1


@pytest.mark.parametrize("name", LISTINGS)
@pytest.mark.parametrize(
    ("rows", "page_size", "expected_pages"),
    [(1, 1, 1), (5, 1, 5), (6, 3, 2), (7, 3, 3), (7, 100, 1)],
    ids=["one-row", "page-of-one", "exact-multiple", "multiple-plus-one", "one-big-page"],
)
@pytest.mark.parametrize(
    "order",
    [None, Order.ASC, Order.DESC],
    ids=["default", "asc", "desc"],
)
async def test_walk_returns_every_row_once_in_order(
    name,
    rows,
    page_size,
    expected_pages,
    order,
):
    fetch, ids = await _listing(name, rows)

    pages = await helpers.walk_pages(fetch, page_size=page_size, order=order)

    assert _ids(pages) == (ids[::-1] if order == Order.DESC else ids)
    assert len(pages) == expected_pages
    assert {page.total_count for page in pages} == {rows}


@pytest.mark.parametrize("name", LISTINGS)
async def test_empty_listing_has_no_items_and_no_token(name):
    fetch = _search() if name == "search" else _links(uuid.uuid4())

    page = await fetch(PageParams(page_size=PAGE_SIZE))

    assert (page.items, page.next_token, page.total_count) == ([], None, 0)


async def test_search_orders_by_material_chapter_number_page_then_id():
    first_material, second_material = sorted(
        [await factories.insert_material(), await factories.insert_material()],
        key=str,
    )
    expected = [
        await factories.insert_note(material_id=material_id, chapter=chapter, page=page)
        for material_id, chapter, page in [
            (second_material, "1", 1),
            (first_material, "10", 1),
            (first_material, "2", 30),
            (first_material, "2", 4),
            (first_material, "Chapter 2", 4),
            (first_material, "", 500),
        ]
    ]
    pages = await helpers.walk_pages(_search(), page_size=2)

    tie = sorted(expected[3:5], key=str)
    assert _ids(pages) == [expected[5], *tie, expected[2], expected[1], expected[0]]


async def test_links_order_by_note_number_not_by_sort_key():
    target, links = await _insert_links(4)

    pages = await helpers.walk_pages(_links(target), page_size=3)

    notes = helpers.page_items(pages)
    assert [note.note_id for note in notes] == links
    assert [note.note_number for note in notes] == [2, 3, 4, 5]
    assert [note.page for note in notes] == [4, 3, 2, 1]


async def test_links_exclude_deleted_and_foreign_links():
    target, links = await _insert_links(3)
    material_id = await factories.insert_material()
    other_target = await factories.insert_note(material_id=material_id)
    await factories.insert_note(material_id=material_id, link_id=other_target)
    await notes_db.delete_note(note_id=links[1])

    page = await notes_db.get_links_from_page(note_id=str(target), params=PageParams())

    assert [note.note_id for note in page.items] == [links[0], links[2]]
    assert page.total_count == 2
    assert [note.links_count for note in page.items] == [0, 0]


async def test_search_token_anchors_on_the_first_row_of_the_next_page():
    ids = await _insert_search_notes(PAGE_SIZE + 2)
    params = PageParams(page_size=PAGE_SIZE)

    page = await _search()(params)

    assert helpers.decode_token(page.next_token) == {
        "params": {
            "order": "asc",
            "max_items": str(PAGE_SIZE),
            "material_id": "",
            "query": "",
            "tags": "",
        },
        "continue_from": {"cursor": await _sort_key(ids[PAGE_SIZE])},
    }


async def test_links_token_anchors_on_the_first_row_of_the_next_page():
    target, links = await _insert_links(PAGE_SIZE + 2)

    page = await _links(target)(PageParams(page_size=PAGE_SIZE, order=Order.DESC))

    # descending: the page holds the three highest note numbers (6, 5, 4), the anchor is number 3
    anchor = links[1]
    assert helpers.decode_token(page.next_token) == {
        "params": {"order": "desc", "max_items": str(PAGE_SIZE), "note_id": str(target)},
        "continue_from": {"cursor": f"0000000003$${await _sort_key(anchor)}"},
    }


async def test_search_token_records_every_filter():
    material_id = await factories.insert_material()
    for page in range(3):
        await factories.insert_note(material_id=material_id, page=page, tags=["b", "a"])

    page = await _search(
        material_id=material_id,
        query="Слово",
        tags={"b", "a"},
        note_ids=None,
    )(
        PageParams(page_size=1),
    )

    assert helpers.decode_token(page.next_token)["params"] == {
        "order": "asc",
        "max_items": "1",
        "material_id": str(material_id),
        "query": "Слово",
        "tags": "a,b",
    }


@pytest.mark.parametrize("name", LISTINGS)
async def test_token_is_url_safe(name):
    fetch, _ = await _listing(name, 2)

    page = await fetch(PageParams(page_size=1))

    assert page.next_token is not None
    assert set(page.next_token) <= set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=",
    )


CHANGED_SEARCH_REQUESTS = {
    "page-size": ({}, {"page_size": 3}),
    "order": ({}, {"order": Order.DESC}),
    "material": ({"material_id": uuid.UUID(int=1)}, {}),
    "tags": ({"tags": {"a"}}, {}),
    "query": ({"query": "other"}, {}),
}


@pytest.mark.parametrize("case", CHANGED_SEARCH_REQUESTS)
async def test_search_rejects_a_token_issued_for_another_request(case):
    await _insert_search_notes(4)
    changed_filters, changed_params = CHANGED_SEARCH_REQUESTS[case]
    first = await _search()(PageParams(page_size=2))
    params = PageParams(page_size=2, next_token=first.next_token).model_copy(
        update=changed_params,
    )

    with pytest.raises(database.InvalidNextTokenException, match="^Invalid nextToken$"):
        await _search(**changed_filters)(params)


async def test_search_accepts_the_default_order_spelled_out():
    ids = await _insert_search_notes(3)
    first = await _search()(PageParams(page_size=2))

    second = await _search()(
        PageParams(page_size=2, next_token=first.next_token, order=Order.ASC),
    )

    assert [note.note_id for note in second.items] == ids[2:]


async def test_search_token_does_not_record_note_ids_current_behaviour():
    ids = await _insert_search_notes(4)
    first = await _search(note_ids=ids)(PageParams(page_size=2))

    second = await _search(note_ids=ids[3:])(
        PageParams(page_size=2, next_token=first.next_token),
    )

    # note_ids are derived from `query`, which the token does record
    assert [note.note_id for note in second.items] == ids[3:]


@pytest.mark.parametrize(
    "changed",
    [{"page_size": 3}, {"order": Order.DESC}],
    ids=["page-size", "order"],
)
async def test_links_reject_a_token_with_changed_page_params(changed):
    target, _ = await _insert_links(4)
    first = await _links(target)(PageParams(page_size=2))
    params = PageParams(page_size=2, next_token=first.next_token).model_copy(
        update=changed,
    )

    with pytest.raises(database.InvalidNextTokenException, match="^Invalid nextToken$"):
        await _links(target)(params)


async def test_links_reject_a_token_of_another_note():
    target, _ = await _insert_links(4)
    other_target, _ = await _insert_links(4)
    first = await _links(target)(PageParams(page_size=2))

    with pytest.raises(database.InvalidNextTokenException, match="^Invalid nextToken$"):
        await _links(other_target)(PageParams(page_size=2, next_token=first.next_token))


async def test_links_token_is_bound_to_the_spelling_of_the_note_id_current_behaviour():
    target, _ = await _insert_links(4)
    first = await _links(target)(PageParams(page_size=2))

    with pytest.raises(database.InvalidNextTokenException, match="^Invalid nextToken$"):
        await _links(str(target).upper())(
            PageParams(page_size=2, next_token=first.next_token),
        )


@pytest.mark.parametrize("name", LISTINGS)
async def test_token_of_the_other_listing_is_rejected(name):
    search_fetch, _ = await _listing("search", 3)
    links_fetch, _ = await _listing("links", 3)
    search_token = (await search_fetch(PageParams(page_size=1))).next_token
    links_token = (await links_fetch(PageParams(page_size=1))).next_token

    fetch, foreign_token = (
        (search_fetch, links_token) if name == "search" else (links_fetch, search_token)
    )

    with pytest.raises(database.InvalidNextTokenException, match="^Invalid nextToken$"):
        await fetch(PageParams(page_size=1, next_token=foreign_token))


SEARCH_TOKEN_PARAMS = {
    "order": "asc",
    "max_items": "2",
    "material_id": "",
    "query": "",
    "tags": "",
}
MALFORMED_TOKENS = {
    "not-base64": "%%%",
    "bad-padding": "abc",
    "not-json": helpers.encode_token("x")[:-2] + "!!",
    "json-string": helpers.encode_token("token"),
    "json-list": helpers.encode_token([SEARCH_TOKEN_PARAMS, {"cursor": "a"}]),
    "empty-object": helpers.encode_token({}),
    "missing-continue-from": helpers.encode_token({"params": SEARCH_TOKEN_PARAMS}),
    "extra-key": helpers.encode_token(
        {"params": SEARCH_TOKEN_PARAMS, "continue_from": {"cursor": "a"}, "extra": 1},
    ),
    "params-not-a-map": helpers.encode_token(
        {"params": "x", "continue_from": {"cursor": "a"}},
    ),
    "non-string-param": helpers.encode_token(
        {
            "params": {**SEARCH_TOKEN_PARAMS, "max_items": 2},
            "continue_from": {"cursor": "a"},
        },
    ),
    "non-string-cursor": helpers.encode_token(
        {"params": SEARCH_TOKEN_PARAMS, "continue_from": {"cursor": 1}},
    ),
    "nul-in-cursor": helpers.encode_token(
        {"params": SEARCH_TOKEN_PARAMS, "continue_from": {"cursor": "a\x00b"}},
    ),
    "no-cursor": helpers.encode_token(
        {"params": SEARCH_TOKEN_PARAMS, "continue_from": {}},
    ),
    "empty-string": "",
}


@pytest.mark.parametrize("token", MALFORMED_TOKENS.values(), ids=list(MALFORMED_TOKENS))
async def test_search_rejects_a_malformed_token(token):
    await _insert_search_notes(3)

    with pytest.raises(database.InvalidNextTokenException):
        await _search()(PageParams(page_size=2, next_token=token))


@pytest.mark.parametrize(
    "token",
    [
        MALFORMED_TOKENS["not-base64"],
        MALFORMED_TOKENS["json-list"],
        MALFORMED_TOKENS["no-cursor"],
    ],
    ids=["not-base64", "json-list", "no-cursor"],
)
async def test_links_reject_a_malformed_token(token):
    target, _ = await _insert_links(3)

    with pytest.raises(database.InvalidNextTokenException):
        await _links(target)(PageParams(page_size=2, next_token=token))


async def test_rejected_token_does_not_touch_the_database():
    await _insert_search_notes(3)

    with (
        helpers.captured_statements() as statements,
        pytest.raises(
            database.InvalidNextTokenException,
        ),
    ):
        await _search()(PageParams(page_size=2, next_token=MALFORMED_TOKENS["json-list"]))

    assert statements == []


# the links cursor is parsed into (note_number, sort_key), the search one is a sort_key
FORGED_CURSORS = {
    "search": {"end": "~", "start": ""},
    "links": {"end": "2147483647$$~", "start": "0000000000$$"},
}


@pytest.mark.parametrize("name", LISTINGS)
@pytest.mark.parametrize(
    ("position", "order", "expected_slice"),
    [
        ("end", Order.ASC, slice(0, 0)),
        ("start", Order.ASC, slice(0, 2)),
        ("start", Order.DESC, slice(0, 0)),
        ("end", Order.DESC, slice(None, None, -1)),
    ],
    ids=[
        "asc-past-the-end",
        "asc-before-the-start",
        "desc-past-the-end",
        "desc-before-the-start",
    ],
)
async def test_forged_cursor_gives_a_consistent_page(name, position, order, expected_slice):
    cursor = FORGED_CURSORS[name][position]
    fetch, ids = await _listing(name, 3)
    first = await fetch(PageParams(page_size=2, order=order))

    page = await fetch(
        PageParams(
            page_size=2,
            order=order,
            next_token=helpers.with_cursor(first.next_token, cursor),
        ),
    )

    assert [note.note_id for note in page.items] == ids[expected_slice][:2]
    assert page.total_count == 3


@pytest.mark.parametrize("name", LISTINGS)
async def test_row_inserted_after_the_cursor_appears_in_the_walk(name):
    fetch, ids = await _listing(name, 4)
    first = await fetch(PageParams(page_size=2))
    material_id = (await factories.fetch_row(models.Notes, ids[0]))["material_id"]
    link_id = (await factories.fetch_row(models.Notes, ids[0]))["link_id"]

    late = await factories.insert_note(
        material_id=material_id,
        link_id=link_id,
        page=1000,
    )
    rest = [await fetch(PageParams(page_size=2, next_token=first.next_token))]
    while (token := rest[-1].next_token) is not None:
        rest.append(await fetch(PageParams(page_size=2, next_token=token)))

    walked = [note.note_id for note in first.items] + _ids(rest)
    assert walked == [*ids, late]
    assert rest[-1].total_count == 5


async def test_row_inserted_before_the_cursor_is_not_returned_and_nothing_repeats():
    ids = await _insert_search_notes(4)
    material_id = (await factories.fetch_row(models.Notes, ids[0]))["material_id"]
    first = await _search()(PageParams(page_size=2))

    await factories.insert_note(material_id=material_id, page=0)
    second = await _search()(PageParams(page_size=2, next_token=first.next_token))

    assert [note.note_id for note in first.items] == ids[:2]
    assert [note.note_id for note in second.items] == ids[2:]
    assert second.next_token is None
    assert second.total_count == 5


@pytest.mark.parametrize("name", LISTINGS)
async def test_walk_continues_when_the_anchor_row_is_deleted(name):
    fetch, ids = await _listing(name, 5)
    first = await fetch(PageParams(page_size=2))

    await notes_db.delete_note(note_id=ids[2])
    second = await fetch(PageParams(page_size=2, next_token=first.next_token))

    assert [note.note_id for note in second.items] == ids[3:]
    assert second.next_token is None
    assert second.total_count == 4


async def test_search_skips_a_note_moved_behind_the_cursor_by_an_update_current_behaviour():
    ids = await _insert_search_notes(4)
    material_id = (await factories.fetch_row(models.Notes, ids[0]))["material_id"]
    first = await _search()(PageParams(page_size=2))

    # update_note rewrites sort_key, the ordering key of the listing
    await notes_db.update_note(
        note_id=ids[3],
        material_id=material_id,
        link_id=None,
        title=None,
        content="Note content.",
        page=0,
        chapter="1",
        tags=[],
    )
    second = await _search()(PageParams(page_size=2, next_token=first.next_token))

    walked = [note.note_id for note in [*first.items, *second.items]]
    assert walked == ids[:3]
    assert ids[3] not in walked


async def _plan_of(fetch: Fetch, params: PageParams) -> str:
    with helpers.captured_statements() as statements:
        await fetch(params)

    statement, parameters = statements[0]
    assert "LIMIT" in statement
    return await helpers.explain(statement, parameters)


@pytest.mark.parametrize("order", [Order.ASC, Order.DESC], ids=["asc", "desc"])
async def test_search_first_page_reads_the_sort_key_index_without_sorting(order):
    await _insert_search_notes(5)

    plan = await _plan_of(_search(), PageParams(page_size=2, order=order))

    assert "notes_sort_key_key" in plan
    assert "Sort" not in plan


@pytest.mark.parametrize("order", [Order.ASC, Order.DESC], ids=["asc", "desc"])
async def test_search_next_page_seeks_the_sort_key_index(order):
    await _insert_search_notes(5)
    first = await _search()(PageParams(page_size=2, order=order))

    plan = await _plan_of(
        _search(),
        PageParams(page_size=2, order=order, next_token=first.next_token),
    )

    assert "notes_sort_key_key" in plan
    assert "Index Cond: ((sort_key)::text" in plan
    assert "Sort" not in plan


async def test_search_by_material_reads_the_sort_key_index_without_sorting():
    ids = await _insert_search_notes(5)
    material_id = (await factories.fetch_row(models.Notes, ids[0]))["material_id"]
    fetch = _search(material_id=material_id)
    first = await fetch(PageParams(page_size=2))

    plan = await _plan_of(fetch, PageParams(page_size=2, next_token=first.next_token))

    assert "notes_sort_key_key" in plan
    assert "Sort" not in plan


@pytest.mark.parametrize("order", [Order.ASC, Order.DESC], ids=["asc", "desc"])
async def test_links_page_is_read_from_the_links_index_without_sorting(order):
    target, _ = await _insert_links(5)
    first_plan = await _plan_of(_links(target), PageParams(page_size=2, order=order))
    first = await _links(target)(PageParams(page_size=2, order=order))

    next_plan = await _plan_of(
        _links(target),
        PageParams(page_size=2, order=order, next_token=first.next_token),
    )

    for plan in (first_plan, next_plan):
        assert "ix_notes_link_id_note_number_sort_key" in plan, plan
        assert "Sort" not in plan, plan
    assert re.search(
        r"Index Cond: \(\(link_id = .*ROW\(note_number, \(sort_key\)::text\) [<>]= ROW\(",
        next_plan,
    ), next_plan


async def test_links_count_subquery_reads_the_links_index():
    await _insert_search_notes(5)

    plan = await _plan_of(_search(), PageParams(page_size=2))

    assert "Seq Scan on notes" not in plan, plan
    assert re.search(
        r"Index (Only )?Scan using ix_notes_link_id_note_number_sort_key on notes\b", plan
    ), plan
    assert "Index Cond: (link_id = n.note_id)" in plan, plan


@pytest.mark.parametrize("name", LISTINGS)
async def test_token_with_a_lone_surrogate_cursor_is_rejected_as_invalid(name):
    fetch, _ = await _listing(name, 3)
    first = await fetch(PageParams(page_size=2))
    token = helpers.with_cursor(first.next_token, "\ud800")

    with pytest.raises(database.InvalidNextTokenException):
        await fetch(PageParams(page_size=2, next_token=token))
