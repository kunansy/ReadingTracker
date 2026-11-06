import base64
import datetime
import json
import uuid

import pytest
from pydantic import ValidationError

from tracker.common import database, pagination, sort_keys


@pytest.mark.parametrize(
    ("chapter", "expected"),
    (
        ("", 0),
        (None, 0),
        ("Introduction", 0),
        ("0", 0),
        ("007", 7),
        ("1.2", 12),
        ("Chapter 3", 3),
        ("12345678901234", 12345678901234),
    ),
)
def test_chapter_int(chapter, expected):
    assert sort_keys.chapter_int(chapter) == expected


def test_pad_int_does_not_truncate():
    assert sort_keys.pad_int(7) == "0000000007"
    assert sort_keys.pad_int("12345678901234") == "12345678901234"


def test_material_sort_key():
    material_id = uuid.uuid4()
    added_at = datetime.datetime(2024, 1, 2, 3, 4, 5, 6)

    result = sort_keys.material_sort_key(added_at=added_at, material_id=material_id)

    assert result == f"2024-01-02T03:04:05.000006$${material_id}"


def test_reading_log_sort_key():
    material_id, log_id = uuid.uuid4(), uuid.uuid4()

    result = sort_keys.reading_log_sort_key(
        material_id=material_id,
        date=datetime.date(2024, 1, 2),
        log_id=log_id,
    )

    assert result == f"{material_id}$$2024-01-02$${log_id}"


def test_note_sort_key():
    material_id, note_id = uuid.uuid4(), uuid.uuid4()

    result = sort_keys.note_sort_key(
        material_id=material_id,
        chapter="Part 1.2",
        page=34,
        note_id=note_id,
    )

    assert result == f"{material_id}$$0000000012$$0000000034$${note_id}"


def test_note_sort_keys_order_by_chapter_then_page():
    material_id = uuid.uuid4()
    notes = [("10", 1), ("2", 50), ("2", 3), ("", 99), ("1.1", 0)]

    keys = [
        sort_keys.note_sort_key(
            material_id=material_id,
            chapter=chapter,
            page=page,
            note_id=uuid.uuid4(),
        )
        for chapter, page in notes
    ]

    ordered = [notes[keys.index(key)] for key in sorted(keys)]
    assert ordered == [("", 99), ("2", 3), ("2", 50), ("10", 1), ("1.1", 0)]


def test_datetime_sort_keys_order_by_time():
    base = datetime.datetime(2024, 1, 1)
    times = [base + datetime.timedelta(microseconds=ms) for ms in (999_999, 1, 10, 0)]

    keys = [sort_keys.card_sort_key(added_at=t, card_id=uuid.uuid4()) for t in times]

    assert [times[keys.index(key)] for key in sorted(keys)] == sorted(times)


@pytest.mark.parametrize("page_size", (0, -1, pagination.MAX_PAGE_SIZE + 1))
def test_page_params_rejects_page_size(page_size):
    with pytest.raises(ValidationError):
        pagination.PageParams(page_size=page_size)


def test_page_params_defaults():
    params = pagination.PageParams()

    assert params.next_token is None
    assert params.page_size == pagination.DEFAULT_PAGE_SIZE


PARAMS = {"order": "asc", "max_items": "20", "material_id": ""}


def _raw_token(payload: object) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


@pytest.mark.parametrize(
    "continue_from",
    (
        {"cursor": "$$"},
        {"cursor": "0000000012$$ö$$x"},
        {"cursor": "a" * 600, "start_date": "2024-01-02"},
    ),
)
def test_next_token_round_trip(continue_from):
    token = pagination.encode_next_token(PARAMS, continue_from)

    assert pagination.decode_and_check_next_token(token, PARAMS) == continue_from


@pytest.mark.parametrize(
    "token",
    (
        "~",
        "a",
        "abc$",
        "gA==",
        "YWJ",
        base64.urlsafe_b64encode(b"\xff").decode(),
        base64.urlsafe_b64encode(b"not json").decode(),
        _raw_token([]),
        _raw_token({"params": PARAMS}),
        _raw_token({"params": PARAMS, "continue_from": {"cursor": "a"}, "x": {}}),
        _raw_token({"params": PARAMS, "continue_from": {"cursor": 1}}),
        _raw_token({"params": PARAMS, "continue_from": ["a"]}),
        _raw_token({"params": PARAMS, "continue_from": {"cursor": "a\x00b"}}),
        _raw_token({"params": PARAMS, "continue_from": {}}),
    ),
)
def test_decode_rejects_malformed_token(token):
    with pytest.raises(database.InvalidNextTokenException):
        pagination.decode_and_check_next_token(token, PARAMS)


@pytest.mark.parametrize(
    "changed",
    (
        {"order": "desc"},
        {"max_items": "21"},
        {"material_id": "x"},
        {"extra": ""},
    ),
)
def test_decode_rejects_other_params(changed):
    token = pagination.encode_next_token(PARAMS, {"cursor": "a"})

    with pytest.raises(database.InvalidNextTokenException):
        pagination.decode_and_check_next_token(token, PARAMS | changed)


def test_page_params_rejects_too_long_token():
    with pytest.raises(ValidationError):
        pagination.PageParams(next_token="a" * (pagination.MAX_TOKEN_LENGTH + 1))


def test_page_request_binds_order_page_size_and_filters():
    request = pagination.page_request(
        pagination.PageParams(page_size=5),
        default_order=pagination.Order.DESC,
        material_id=None,
        tags={"b", "a"},
        is_outlined=False,
    )

    assert request.order == pagination.Order.DESC
    assert request.continue_from is None
    assert request.params == {
        "order": "desc",
        "max_items": "5",
        "material_id": "",
        "tags": "a,b",
        "is_outlined": "False",
    }


def test_page_request_reads_cursor_from_token():
    first = pagination.page_request(
        pagination.PageParams(),
        default_order=pagination.Order.ASC,
        material_id=None,
    )
    token = first.next_token("cursor-value", start_date="2024-01-01")
    assert token is not None

    request = pagination.page_request(
        pagination.PageParams(next_token=token),
        default_order=pagination.Order.ASC,
        material_id=None,
    )

    assert request.cursor == "cursor-value"
    assert request.continue_from == {"cursor": "cursor-value", "start_date": "2024-01-01"}


def test_page_request_next_token_is_none_without_cursor():
    request = pagination.page_request(
        pagination.PageParams(),
        default_order=pagination.Order.ASC,
    )

    assert request.next_token(None) is None


def test_page_params_rejects_unknown_order():
    with pytest.raises(ValidationError):
        pagination.PageParams(order="random")


class _Row:
    def __init__(self, cursor: str) -> None:
        self.cursor = cursor


@pytest.mark.parametrize(
    ("rows_count", "page_size", "expected_len", "expected_cursor"),
    (
        (0, 2, 0, None),
        (2, 2, 2, None),
        (3, 2, 2, "2"),
        (5, 2, 2, "2"),
    ),
)
def test_split_page(rows_count, page_size, expected_len, expected_cursor):
    rows = [_Row(str(i)) for i in range(rows_count)]

    page, next_cursor = pagination.split_page(rows, page_size)

    assert len(page) == expected_len
    assert next_cursor == expected_cursor
