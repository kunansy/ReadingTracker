import datetime
import uuid

import pytest
from pydantic import ValidationError

from tracker.common import pagination, sort_keys


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


@pytest.mark.parametrize(
    "cursor",
    ("$$", "2024-01-02$$abc", "0000000012$$ö$$x", "a" * 600 + "$$b"),
)
def test_token_round_trip(cursor):
    token = pagination.encode_token(cursor)

    assert pagination.decode_token(token) == cursor
    assert pagination.PageParams(next_token=token).next_token == token


@pytest.mark.parametrize(
    "token",
    (
        "~",
        "a",
        "abc$",
        "gA==",
        "YWJ",
        pagination.encode_token("a\x00$$b"),
        pagination.encode_token("no separator"),
        pagination.encode_token("a" * pagination.MAX_TOKEN_LENGTH + "$$b"),
    ),
)
def test_page_params_rejects_invalid_token(token):
    with pytest.raises(ValidationError):
        pagination.PageParams(next_token=token)


def test_page_params_rejects_unknown_order():
    with pytest.raises(ValidationError):
        pagination.PageParams(order="random")


class _Row:
    def __init__(self, cursor: str) -> None:
        self.cursor = cursor


@pytest.mark.parametrize(
    ("rows_count", "page_size", "expected_len", "expected_token"),
    (
        (0, 2, 0, None),
        (2, 2, 2, None),
        (3, 2, 2, pagination.encode_token("2")),
        (5, 2, 2, pagination.encode_token("2")),
    ),
)
def test_split_page(rows_count, page_size, expected_len, expected_token):
    rows = [_Row(str(i)) for i in range(rows_count)]

    page, next_token = pagination.split_page(
        rows,
        pagination.PageParams(page_size=page_size),
    )

    assert len(page) == expected_len
    assert next_token == expected_token
