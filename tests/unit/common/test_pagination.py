import base64
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
import sqlalchemy.sql as sa
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from tracker.common import database, pagination
from tracker.common.pagination import Order, Page, PageParams, PageRequest
from tracker.models import models


PARAMS = {"order": "asc", "max_items": "20", "material_id": ""}

# base64url of the canonical JSON; a change of the wire format must redden these
PINNED_TOKEN = (
    "eyJjb250aW51ZV9mcm9tIjp7ImN1cnNvciI6IjIwMjQtMDEtMDJUMDM6MDQ6MDUuMDAwMDA2JCR4In0s"
    "InBhcmFtcyI6eyJtYXRlcmlhbF9pZCI6IiIsIm1heF9pdGVtcyI6IjIwIiwib3JkZXIiOiJhc2MifX0="
)
PINNED_CONTINUE_FROM = {"cursor": "2024-01-02T03:04:05.000006$$x"}
PINNED_URLSAFE_TOKEN = (
    "eyJjb250aW51ZV9mcm9tIjp7ImN1cnNvciI6Ilx1MDBmNj8-Iiwic3RhcnRfZGF0ZSI6IjIwMjQtMDEt"
    "MDIifSwicGFyYW1zIjp7Im1heF9pdGVtcyI6IjUiLCJvcmRlciI6ImRlc2MifX0="
)


def _raw_token(payload: object) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _compile(stmt: sa.ClauseElement) -> str:
    compiled = stmt.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    return " ".join(str(compiled).split())


def _request(
    *,
    order: Order = Order.ASC,
    page_size: int = 2,
    cursor: str | None = None,
    params: dict[str, str] | None = None,
) -> PageRequest:
    return PageRequest(
        order=order,
        page_size=page_size,
        params=params or {},
        continue_from={"cursor": cursor} if cursor is not None else None,
    )


class _Row:
    def __init__(self, cursor: str) -> None:
        self.cursor = cursor


class _FakeSession:
    def __init__(self, rows: list[_Row], total: int | None) -> None:
        self._rows = rows
        self._total = total
        self.executed: list[sa.Select] = []
        self.scalars: list[sa.Select] = []

    async def execute(self, stmt: sa.Select) -> SimpleNamespace:
        self.executed.append(stmt)
        return SimpleNamespace(all=lambda: self._rows)

    async def scalar(self, stmt: sa.Select) -> int | None:
        self.scalars.append(stmt)
        return self._total


@pytest.fixture
def fake_session(mocker):
    def _install(rows: list[_Row], total: int | None) -> _FakeSession:
        ses = _FakeSession(rows, total)

        @asynccontextmanager
        async def _session(**_kwargs):
            yield ses

        mocker.patch("tracker.common.database.session", _session)
        return ses

    return _install


STMT = sa.select(models.Materials.c.material_id).where(models.Materials.c.pages > 3)
CURSOR_EXPR = pagination.cursor(models.Materials.c.sort_key)


def test_encode_next_token_wire_format_is_pinned():
    token = pagination.encode_next_token(PARAMS, PINNED_CONTINUE_FROM)

    assert token == PINNED_TOKEN


def test_encode_next_token_uses_urlsafe_alphabet_and_ascii_json():
    token = pagination.encode_next_token(
        {"order": "desc", "max_items": "5"},
        {"cursor": "ö?>", "start_date": "2024-01-02"},
    )

    assert token == PINNED_URLSAFE_TOKEN
    assert "+" not in token
    assert "/" not in token


def test_encode_next_token_does_not_depend_on_key_order():
    first = pagination.encode_next_token({"a": "1", "b": "2"}, {"cursor": "c", "x": "y"})
    second = pagination.encode_next_token({"b": "2", "a": "1"}, {"x": "y", "cursor": "c"})

    assert first == second


def test_decode_pinned_token_returns_continue_from():
    result = pagination.decode_and_check_next_token(PINNED_TOKEN, PARAMS)

    assert result == PINNED_CONTINUE_FROM


@pytest.mark.parametrize(
    "continue_from",
    [
        {"cursor": ""},
        {"cursor": "$$"},
        {"cursor": "0000000012$$ö$$x"},
        {"cursor": "Заметка 🙂 \" \\ ' \n"},
        {"cursor": "a" * 600, "start_date": "2024-01-02"},
    ],
    ids=["empty-cursor", "separator-only", "latin-1", "unicode-and-quotes", "extra-key"],
)
def test_next_token_round_trip(continue_from):
    token = pagination.encode_next_token(PARAMS, continue_from)

    assert pagination.decode_and_check_next_token(token, PARAMS) == continue_from


@pytest.mark.parametrize(
    "token",
    [
        "",
        "~",
        "a",
        "abc$",
        "YWJ",
        "eyJ9 ",
        "токен",
    ],
    ids=[
        "empty",
        "not-in-alphabet",
        "too-short",
        "bad-symbol",
        "no-padding",
        "space",
        "non-ascii",
    ],
)
def test_decode_rejects_bad_base64(token):
    with pytest.raises(
        database.InvalidNextTokenException, match="^next_token is malformed$"
    ):
        pagination.decode_and_check_next_token(token, PARAMS)


@pytest.mark.parametrize(
    "raw",
    [
        b"\xff",
        b"\x80",
        b"not json",
        b'{"params": {}',
        b"[" * 3072,
    ],
    ids=["invalid-utf8", "continuation-byte", "plain-text", "truncated", "deep-nesting"],
)
def test_decode_rejects_bad_json(raw):
    token = base64.urlsafe_b64encode(raw).decode()

    with pytest.raises(
        database.InvalidNextTokenException, match="^next_token is malformed$"
    ):
        pagination.decode_and_check_next_token(token, PARAMS)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        "text",
        1,
        None,
        {},
        {"params": PARAMS},
        {"continue_from": {"cursor": "a"}},
        {"params": PARAMS, "continue_from": {"cursor": "a"}, "x": {}},
        {"params": PARAMS, "continue": {"cursor": "a"}},
    ],
    ids=[
        "list",
        "string",
        "number",
        "null",
        "empty-dict",
        "no-continue-from",
        "no-params",
        "extra-key",
        "renamed-key",
    ],
)
def test_decode_rejects_wrong_shape(payload):
    with pytest.raises(
        database.InvalidNextTokenException, match="^next_token is malformed$"
    ):
        pagination.decode_and_check_next_token(_raw_token(payload), PARAMS)


@pytest.mark.parametrize(
    "payload",
    [
        {"params": PARAMS, "continue_from": {"cursor": 1}},
        {"params": PARAMS, "continue_from": {"cursor": None}},
        {"params": PARAMS, "continue_from": {"cursor": ["a"]}},
        {"params": PARAMS, "continue_from": ["a"]},
        {"params": PARAMS, "continue_from": "cursor"},
        {"params": PARAMS, "continue_from": {"cursor": "a\x00b"}},
        {"params": PARAMS | {"material_id": "\x00"}, "continue_from": {"cursor": "a"}},
        {"params": [PARAMS], "continue_from": {"cursor": "a"}},
        {"params": PARAMS | {"max_items": 20}, "continue_from": {"cursor": "a"}},
    ],
    ids=[
        "int-cursor",
        "null-cursor",
        "list-cursor",
        "continue-from-is-list",
        "continue-from-is-string",
        "nul-in-cursor",
        "nul-in-params",
        "params-is-list",
        "int-param",
    ],
)
def test_decode_rejects_non_string_maps(payload):
    with pytest.raises(
        database.InvalidNextTokenException, match="^next_token is malformed$"
    ):
        pagination.decode_and_check_next_token(_raw_token(payload), PARAMS)


@pytest.mark.parametrize(
    "request_params",
    [
        PARAMS | {"order": "desc"},
        PARAMS | {"max_items": "21"},
        PARAMS | {"material_id": "x"},
        PARAMS | {"extra": ""},
        {"order": "asc", "max_items": "20"},
        {},
    ],
    ids=["order", "page-size", "filter", "added-filter", "removed-filter", "no-params"],
)
def test_decode_rejects_token_issued_for_other_params(request_params):
    token = pagination.encode_next_token(PARAMS, {"cursor": "a"})

    with pytest.raises(
        database.InvalidNextTokenException,
        match="^next_token does not match the request parameters$",
    ):
        pagination.decode_and_check_next_token(token, request_params)


@pytest.mark.parametrize(
    "continue_from",
    [{}, {"start_date": "2024-01-02"}, {"Cursor": "a"}],
    ids=["empty", "other-key", "wrong-case"],
)
def test_decode_rejects_token_without_cursor(continue_from):
    token = _raw_token({"params": PARAMS, "continue_from": continue_from})

    with pytest.raises(
        database.InvalidNextTokenException, match="^next_token has no cursor$"
    ):
        pagination.decode_and_check_next_token(token, PARAMS)


def test_decode_accepts_standard_base64_alphabet_current_behaviour():
    payload = {"params": {}, "continue_from": {"cursor": "~~~???>>>"}}
    token = base64.b64encode(json.dumps(payload).encode()).decode()
    assert "+" in token
    assert "/" in token

    result = pagination.decode_and_check_next_token(token, {})

    assert result == {"cursor": "~~~???>>>"}


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: tracker/common/pagination.py:47 a lone surrogate in the token passes "
        "_is_token_map although, like NUL, it cannot be sent to Postgres as text"
    ),
)
def test_decode_rejects_cursor_that_cannot_be_encoded_as_utf8():
    token = _raw_token({"params": PARAMS, "continue_from": {"cursor": "\ud800"}})

    with pytest.raises(database.InvalidNextTokenException):
        pagination.decode_and_check_next_token(token, PARAMS)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({}, True),
        ({"a": "b"}, True),
        ({"a": ""}, True),
        ({"a\x00": "b"}, True),
        ({"a": "b\x00"}, False),
        ({"a": 1}, False),
        ({"a": None}, False),
        ({"a": {"b": "c"}}, False),
        ({1: "b"}, False),
        ({"a": "b", "c": 1}, False),
        ([], False),
        ([("a", "b")], False),
        ("ab", False),
        (None, False),
    ],
    ids=[
        "empty-dict",
        "str-to-str",
        "empty-value",
        "nul-in-key",
        "nul-in-value",
        "int-value",
        "none-value",
        "nested",
        "int-key",
        "one-bad-value",
        "list",
        "pairs",
        "string",
        "none",
    ],
)
def test_is_token_map(value, expected):
    assert pagination._is_token_map(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        ("", ""),
        ("text", "text"),
        (0, "0"),
        (False, "False"),
        (True, "True"),
        (set(), ""),
        (frozenset(), ""),
        ({"b", "a", "c"}, "a,b,c"),
        (frozenset({"я", "б"}), "б,я"),
        ({10, 9}, "10,9"),
        (Order.DESC, "desc"),
        (["b", "a"], "['b', 'a']"),
    ],
    ids=[
        "none",
        "empty-string",
        "string",
        "zero",
        "false",
        "true",
        "empty-set",
        "empty-frozenset",
        "set-is-sorted",
        "cyrillic-frozenset",
        "set-sorted-as-strings",
        "str-enum",
        "list-is-not-sorted",
    ],
)
def test_param_value(value, expected):
    assert pagination._param_value(value) == expected


def test_param_value_of_set_does_not_escape_the_separator_current_behaviour():
    one_tag = pagination._param_value({"a,b"})
    two_tags = pagination._param_value({"a", "b"})

    assert one_tag == two_tags == "a,b"


def test_page_params_defaults():
    params = PageParams()

    assert params.next_token is None
    assert params.page_size == 20
    assert params.order is None


@pytest.mark.parametrize("page_size", [1, 100], ids=["min", "max"])
def test_page_params_accepts_boundary_page_sizes(page_size):
    assert PageParams(page_size=page_size).page_size == page_size


@pytest.mark.parametrize("page_size", [0, -1, 101], ids=["zero", "negative", "over-max"])
def test_page_params_rejects_page_size(page_size):
    with pytest.raises(ValidationError):
        PageParams(page_size=page_size)


def test_page_params_accepts_token_of_max_length():
    assert PageParams(next_token="a" * 4096).next_token == "a" * 4096


def test_page_params_rejects_too_long_token():
    with pytest.raises(ValidationError):
        PageParams(next_token="a" * 4097)


def test_page_params_rejects_unknown_order():
    with pytest.raises(ValidationError):
        PageParams(order="random")


def test_page_request_uses_default_order_when_none_is_given():
    request = pagination.page_request(PageParams(), default_order=Order.DESC)

    assert request == PageRequest(
        order=Order.DESC,
        page_size=20,
        params={"order": "desc", "max_items": "20"},
        continue_from=None,
    )


def test_page_request_prefers_explicit_order():
    request = pagination.page_request(
        PageParams(order=Order.ASC),
        default_order=Order.DESC,
    )

    assert request.order == Order.ASC
    assert request.params["order"] == "asc"


def test_page_request_binds_every_filter_type():
    request = pagination.page_request(
        PageParams(page_size=5),
        default_order=Order.DESC,
        material_id=None,
        tags={"b", "a"},
        is_outlined=False,
        query="поиск",
        limit=0,
    )

    assert request.params == {
        "order": "desc",
        "max_items": "5",
        "material_id": "",
        "tags": "a,b",
        "is_outlined": "False",
        "query": "поиск",
        "limit": "0",
    }
    assert request.page_size == 5
    assert request.continue_from is None
    assert request.cursor is None


def test_page_request_reads_continue_from_of_its_own_token():
    first = pagination.page_request(
        PageParams(),
        default_order=Order.ASC,
        material_id=None,
    )
    token = first.next_token("cursor-value", start_date="2024-01-01")

    request = pagination.page_request(
        PageParams(next_token=token),
        default_order=Order.ASC,
        material_id=None,
    )

    assert request.cursor == "cursor-value"
    assert request.continue_from == {"cursor": "cursor-value", "start_date": "2024-01-01"}
    assert request.params == first.params


def test_page_request_accepts_pinned_token():
    request = pagination.page_request(
        PageParams(next_token=PINNED_TOKEN),
        default_order=Order.ASC,
        material_id=None,
    )

    assert request.continue_from == PINNED_CONTINUE_FROM


@pytest.mark.parametrize(
    ("params", "filters"),
    [
        (PageParams(page_size=21), {"material_id": None}),
        (PageParams(order=Order.DESC), {"material_id": None}),
        (PageParams(), {"material_id": "018e9dbe-1d3d-7a5a-b437-9bfa65171b42"}),
        (PageParams(), {}),
        (PageParams(), {"material_id": None, "tags": set()}),
    ],
    ids=["page-size", "order", "filter-value", "filter-removed", "filter-added"],
)
def test_page_request_rejects_token_of_another_request(params, filters):
    params = params.model_copy(update={"next_token": PINNED_TOKEN})

    with pytest.raises(
        database.InvalidNextTokenException,
        match="does not match the request parameters",
    ):
        pagination.page_request(params, default_order=Order.ASC, **filters)


def test_page_request_token_for_none_filter_matches_empty_filter_current_behaviour():
    request = pagination.page_request(
        PageParams(next_token=PINNED_TOKEN),
        default_order=Order.ASC,
        material_id="",
    )

    assert request.cursor == PINNED_CONTINUE_FROM["cursor"]


def test_page_request_rejects_malformed_token():
    with pytest.raises(database.InvalidNextTokenException, match="malformed"):
        pagination.page_request(PageParams(next_token="~"), default_order=Order.ASC)


def test_request_cursor_is_none_without_continue_from():
    assert _request().cursor is None


def test_request_cursor_is_none_for_empty_continue_from():
    request = PageRequest(order=Order.ASC, page_size=1, params={}, continue_from={})

    assert request.cursor is None


def test_request_cursor_keeps_empty_string():
    assert _request(cursor="").cursor == ""


def test_request_next_token_is_none_without_cursor():
    assert _request(params=PARAMS).next_token(None) is None


def test_request_next_token_binds_params_and_cursor():
    request = _request(params=PARAMS)

    token = request.next_token(PINNED_CONTINUE_FROM["cursor"])

    assert token == PINNED_TOKEN


def test_request_next_token_for_empty_cursor_is_still_a_token():
    token = _request(params=PARAMS).next_token("")

    assert pagination.decode_and_check_next_token(token, PARAMS) == {"cursor": ""}


def test_request_next_token_carries_extra_continue_from():
    token = _request(params=PARAMS).next_token("c", start_date="2024-01-02")

    assert pagination.decode_and_check_next_token(token, PARAMS) == {
        "cursor": "c",
        "start_date": "2024-01-02",
    }


def test_page_with_items_keeps_token_and_total():
    page = Page(items=[1, 2], next_token="token", total_count=7)

    result = page.with_items(["a"])

    assert result == Page(items=["a"], next_token="token", total_count=7)
    assert page.items == [1, 2]


def test_page_with_items_keeps_absent_token():
    page = Page(items=[1], next_token=None, total_count=0)

    assert page.with_items([]) == Page(items=[], next_token=None, total_count=0)


@pytest.mark.parametrize(
    ("rows_count", "expected_cursors", "expected_next"),
    [
        (0, [], None),
        (1, ["0"], None),
        (2, ["0", "1"], None),
        (3, ["0", "1"], "2"),
        (5, ["0", "1"], "2"),
    ],
    ids=["empty", "page-size-minus-1", "exactly-page-size", "page-size-plus-1", "more"],
)
def test_split_page(rows_count, expected_cursors, expected_next):
    rows = [_Row(str(i)) for i in range(rows_count)]

    page, next_cursor = pagination.split_page(rows, 2)

    assert [row.cursor for row in page] == expected_cursors
    assert next_cursor == expected_next


def test_datetime_part_formats_with_microseconds():
    expr = pagination.datetime_part(models.Materials.c.added_at)

    assert _compile(expr) == (
        "to_char(materials.added_at, 'YYYY-MM-DD\"T\"HH24:MI:SS.US')"
    )


def test_date_part_formats_iso_date():
    expr = pagination.date_part(models.ReadingLog.c.date)

    assert _compile(expr) == "to_char(reading_log.date, 'YYYY-MM-DD')"


def test_int_part_pads_to_sort_key_width():
    expr = pagination.int_part(models.ReadingLog.c.count)

    assert _compile(expr) == "lpad(CAST(reading_log.count AS TEXT), 10, '0')"


def test_cursor_of_single_part_is_collated():
    assert _compile(CURSOR_EXPR) == 'materials.sort_key COLLATE "C"'


def test_cursor_joins_parts_with_separator():
    expr = pagination.cursor(
        pagination.date_part(models.ReadingLog.c.date),
        pagination.int_part(models.ReadingLog.c.count),
        models.ReadingLog.c.sort_key,
    )

    assert _compile(expr) == (
        "to_char(reading_log.date, 'YYYY-MM-DD') || '$$' || "
        "lpad(CAST(reading_log.count AS TEXT), 10, '0') || '$$' || "
        'reading_log.sort_key COLLATE "C"'
    )


def test_cursor_without_parts_is_an_error():
    with pytest.raises(IndexError):
        pagination.cursor()


def test_paginate_first_page_asc():
    stmt = pagination.paginate(STMT, cursor_expr=CURSOR_EXPR, request=_request())

    assert _compile(stmt) == (
        'SELECT materials.material_id, materials.sort_key COLLATE "C" AS cursor '
        "FROM materials WHERE materials.pages > 3 "
        'ORDER BY materials.sort_key COLLATE "C" ASC LIMIT 3'
    )


def test_paginate_first_page_desc():
    stmt = pagination.paginate(
        STMT,
        cursor_expr=CURSOR_EXPR,
        request=_request(order=Order.DESC),
    )

    assert _compile(stmt) == (
        'SELECT materials.material_id, materials.sort_key COLLATE "C" AS cursor '
        "FROM materials WHERE materials.pages > 3 "
        'ORDER BY materials.sort_key COLLATE "C" DESC LIMIT 3'
    )


def test_paginate_next_page_asc_starts_at_cursor_inclusive():
    stmt = pagination.paginate(
        STMT,
        cursor_expr=CURSOR_EXPR,
        request=_request(cursor="k", page_size=20),
    )

    assert _compile(stmt) == (
        'SELECT materials.material_id, materials.sort_key COLLATE "C" AS cursor '
        "FROM materials WHERE materials.pages > 3 "
        "AND (materials.sort_key COLLATE \"C\") >= 'k' "
        'ORDER BY materials.sort_key COLLATE "C" ASC LIMIT 21'
    )


def test_paginate_next_page_desc_starts_at_cursor_inclusive():
    stmt = pagination.paginate(
        STMT,
        cursor_expr=CURSOR_EXPR,
        request=_request(order=Order.DESC, cursor="k", page_size=100),
    )

    assert _compile(stmt) == (
        'SELECT materials.material_id, materials.sort_key COLLATE "C" AS cursor '
        "FROM materials WHERE materials.pages > 3 "
        "AND (materials.sort_key COLLATE \"C\") <= 'k' "
        'ORDER BY materials.sort_key COLLATE "C" DESC LIMIT 101'
    )


def test_paginate_applies_empty_cursor():
    stmt = pagination.paginate(STMT, cursor_expr=CURSOR_EXPR, request=_request(cursor=""))

    assert "(materials.sort_key COLLATE \"C\") >= ''" in _compile(stmt)


def test_paginate_sends_cursor_as_bound_parameter():
    stmt = pagination.paginate(
        STMT,
        cursor_expr=CURSOR_EXPR,
        request=_request(cursor="a'; DROP TABLE materials; --"),
    )

    compiled = stmt.compile(dialect=postgresql.dialect())

    assert "DROP TABLE" not in str(compiled)
    assert "a'; DROP TABLE materials; --" in compiled.params.values()


def test_paginate_replaces_ordering_of_the_statement():
    stmt = pagination.paginate(
        STMT.order_by(models.Materials.c.title.desc()),
        cursor_expr=CURSOR_EXPR,
        request=_request(),
    )

    compiled = _compile(stmt)

    assert "materials.title" not in compiled
    assert compiled.endswith('ORDER BY materials.sort_key COLLATE "C" ASC LIMIT 3')


def test_paginate_does_not_change_the_given_statement():
    before = _compile(STMT)

    pagination.paginate(STMT, cursor_expr=CURSOR_EXPR, request=_request(cursor="k"))

    assert _compile(STMT) == before


async def test_count_wraps_statement_without_ordering():
    ses = _FakeSession([], 42)

    result = await pagination.count(ses, STMT.order_by(models.Materials.c.title))

    assert result == 42
    assert [_compile(stmt) for stmt in ses.scalars] == [
        "SELECT count(*) AS count_1 FROM (SELECT materials.material_id AS material_id "
        "FROM materials WHERE materials.pages > 3) AS anon_1",
    ]


@pytest.mark.parametrize("total", [None, 0], ids=["none", "zero"])
async def test_count_is_zero_when_database_returns_nothing(total):
    ses = _FakeSession([], total)

    assert await pagination.count(ses, STMT) == 0


@pytest.mark.parametrize(
    ("rows_count", "expected_items", "expected_next"),
    [
        (0, [], None),
        (1, ["item-0"], None),
        (2, ["item-0", "item-1"], None),
        (3, ["item-0", "item-1"], "2"),
    ],
    ids=["empty", "page-size-minus-1", "exactly-page-size", "page-size-plus-1"],
)
async def test_fetch_rows_splits_page_and_maps_items(
    fake_session,
    rows_count,
    expected_items,
    expected_next,
):
    ses = fake_session([_Row(str(i)) for i in range(rows_count)], total=9)

    result = await pagination.fetch_rows(
        STMT,
        cursor_expr=CURSOR_EXPR,
        request=_request(page_size=2),
        to_item=lambda row: f"item-{row.cursor}",
    )

    assert result == (expected_items, expected_next, 9)
    assert len(ses.executed) == 1
    assert len(ses.scalars) == 1


async def test_fetch_rows_executes_paginated_statement_and_counts_the_original(
    fake_session,
):
    ses = fake_session([], total=0)

    await pagination.fetch_rows(
        STMT,
        cursor_expr=CURSOR_EXPR,
        request=_request(order=Order.DESC, cursor="k", page_size=2),
        to_item=lambda row: row,
    )

    assert _compile(ses.executed[0]) == (
        'SELECT materials.material_id, materials.sort_key COLLATE "C" AS cursor '
        "FROM materials WHERE materials.pages > 3 "
        "AND (materials.sort_key COLLATE \"C\") <= 'k' "
        'ORDER BY materials.sort_key COLLATE "C" DESC LIMIT 3'
    )
    assert _compile(ses.scalars[0]) == (
        "SELECT count(*) AS count_1 FROM (SELECT materials.material_id AS material_id "
        "FROM materials WHERE materials.pages > 3) AS anon_1"
    )


async def test_fetch_page_emits_token_when_extra_row_exists(fake_session):
    fake_session([_Row("a"), _Row("b"), _Row("c")], total=3)
    request = _request(page_size=2, params=PARAMS)

    page = await pagination.fetch_page(
        STMT,
        cursor_expr=CURSOR_EXPR,
        request=request,
        to_item=lambda row: row.cursor,
    )

    assert page.items == ["a", "b"]
    assert page.total_count == 3
    assert pagination.decode_and_check_next_token(page.next_token, PARAMS) == {
        "cursor": "c",
    }


async def test_fetch_page_emits_no_token_for_exactly_full_last_page(fake_session):
    fake_session([_Row("a"), _Row("b")], total=2)

    page = await pagination.fetch_page(
        STMT,
        cursor_expr=CURSOR_EXPR,
        request=_request(page_size=2, params=PARAMS),
        to_item=lambda row: row.cursor,
    )

    assert page == Page(items=["a", "b"], next_token=None, total_count=2)


async def test_fetch_page_of_empty_result(fake_session):
    fake_session([], total=None)

    page = await pagination.fetch_page(
        STMT,
        cursor_expr=CURSOR_EXPR,
        request=_request(),
        to_item=lambda row: row.cursor,
    )

    assert page == Page(items=[], next_token=None, total_count=0)
