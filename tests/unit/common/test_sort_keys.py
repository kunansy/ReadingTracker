import datetime
from uuid import UUID

import pytest

from tracker.common import sort_keys


MATERIAL_ID = UUID("018e9dbe-1d3d-7a5a-b437-9bfa65171b42")
OTHER_ID = UUID("1c2fc59d-5313-4615-9290-e8668abe2fc0")


def test_join_puts_separator_between_parts():
    assert sort_keys.join("a", "b", "c") == "a$$b$$c"


def test_join_of_single_part_has_no_separator():
    assert sort_keys.join("a") == "a"


def test_join_of_nothing_is_empty():
    assert sort_keys.join() == ""


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0000000000"),
        (7, "0000000007"),
        ("7", "0000000007"),
        (999_999_999, "0999999999"),
        (9_999_999_999, "9999999999"),
        (10_000_000_000, "10000000000"),
        ("12345678901234", "12345678901234"),
        (2**31 - 1, "2147483647"),
    ],
    ids=[
        "zero",
        "one-digit",
        "string",
        "one-below-width",
        "exactly-width",
        "one-past-width",
        "long-string",
        "int32-max",
    ],
)
def test_pad_int_pads_to_width_and_never_truncates(value, expected):
    assert sort_keys.pad_int(value) == expected


def test_pad_int_keeps_sign_in_front_of_padding():
    assert sort_keys.pad_int(-5) == "-000000005"


@pytest.mark.parametrize(
    ("chapter", "expected"),
    [
        ("", "0"),
        (None, "0"),
        ("Introduction", "0"),
        ("Введение", "0"),
        ("0", "0"),
        ("000", "0"),
        ("007", "7"),
        ("1.2", "12"),
        ("Chapter 3", "3"),
        ("Глава 10, часть 2", "102"),
        ("-5", "5"),
        ("12345678901234", "12345678901234"),
        # string.digits is ASCII only
        ("٣", "0"),
        ("²", "0"),
    ],
    ids=[
        "empty",
        "none",
        "no-digits",
        "cyrillic-no-digits",
        "zero",
        "all-zeroes",
        "leading-zeroes",
        "dotted",
        "prefixed",
        "cyrillic-with-digits",
        "minus-is-dropped",
        "longer-than-width",
        "arabic-indic-digit",
        "superscript-digit",
    ],
)
def test_chapter_digits(chapter, expected):
    assert sort_keys.chapter_digits(chapter) == expected


@pytest.mark.parametrize(
    ("chapter", "expected"),
    [
        ("", 0),
        (None, 0),
        ("Introduction", 0),
        ("0", 0),
        ("007", 7),
        ("1.2", 12),
        ("Chapter 3", 3),
        ("12345678901234", 12345678901234),
    ],
)
def test_chapter_int(chapter, expected):
    assert sort_keys.chapter_int(chapter) == expected


def test_material_sort_key():
    result = sort_keys.material_sort_key(
        added_at=datetime.datetime(2024, 1, 2, 3, 4, 5, 6),
        material_id=MATERIAL_ID,
    )

    assert result == "2024-01-02T03:04:05.000006$$018e9dbe-1d3d-7a5a-b437-9bfa65171b42"


def test_material_sort_key_accepts_string_id():
    result = sort_keys.material_sort_key(
        added_at=datetime.datetime(2024, 12, 31, 23, 59, 59, 999_999),
        material_id="id",
    )

    assert result == "2024-12-31T23:59:59.999999$$id"


def test_card_sort_key():
    result = sort_keys.card_sort_key(
        added_at=datetime.datetime(2024, 1, 2),
        card_id=OTHER_ID,
    )

    assert result == "2024-01-02T00:00:00.000000$$1c2fc59d-5313-4615-9290-e8668abe2fc0"


def test_reading_log_sort_key():
    result = sort_keys.reading_log_sort_key(
        material_id=MATERIAL_ID,
        date=datetime.date(2024, 1, 2),
        log_id=OTHER_ID,
    )

    assert result == (
        "018e9dbe-1d3d-7a5a-b437-9bfa65171b42$$2024-01-02$$"
        "1c2fc59d-5313-4615-9290-e8668abe2fc0"
    )


def test_reading_log_sort_key_drops_time_of_a_datetime():
    result = sort_keys.reading_log_sort_key(
        material_id="m",
        date=datetime.datetime(2024, 1, 2, 23, 59, 59),
        log_id="l",
    )

    assert result == "m$$2024-01-02$$l"


def test_note_sort_key():
    result = sort_keys.note_sort_key(
        material_id=MATERIAL_ID,
        chapter="Part 1.2",
        page=34,
        note_id=OTHER_ID,
    )

    assert result == (
        "018e9dbe-1d3d-7a5a-b437-9bfa65171b42$$0000000012$$0000000034$$"
        "1c2fc59d-5313-4615-9290-e8668abe2fc0"
    )


@pytest.mark.parametrize("chapter", [None, "", "Preface"], ids=["none", "empty", "text"])
def test_note_sort_key_without_chapter_number_uses_zero(chapter):
    result = sort_keys.note_sort_key(
        material_id="m",
        chapter=chapter,
        page=0,
        note_id="n",
    )

    assert result == "m$$0000000000$$0000000000$$n"


def _note_key(chapter: str, page: int) -> str:
    return sort_keys.note_sort_key(
        material_id=MATERIAL_ID,
        chapter=chapter,
        page=page,
        note_id=OTHER_ID,
    )


def test_note_sort_keys_order_by_chapter_then_page():
    notes = [("10", 1), ("2", 50), ("2", 3), ("", 99), ("1.1", 0)]

    ordered = sorted(notes, key=lambda note: _note_key(*note))

    assert ordered == [("", 99), ("2", 3), ("2", 50), ("10", 1), ("1.1", 0)]


def test_note_sort_keys_order_pages_numerically_up_to_int32_max():
    pages = [2**31 - 1, 10, 9, 1_000_000_000, 0, 999_999_999]

    ordered = sorted(pages, key=lambda page: _note_key("1", page))

    assert ordered == sorted(pages)


def test_note_sort_keys_with_more_chapter_digits_than_width_current_behaviour():
    # 11 chapter digits are not padded, so "10000000000" sorts before "9999999999"
    chapters = ["9999999999", "1.0.0.0.0.0.0.0.0.0.0"]

    ordered = sorted(chapters, key=lambda chapter: _note_key(chapter, 1))

    assert ordered == ["1.0.0.0.0.0.0.0.0.0.0", "9999999999"]


def test_note_sort_keys_with_negative_pages_current_behaviour():
    ordered = sorted([-1, -2, 0], key=lambda page: _note_key("1", page))

    assert ordered == [-1, -2, 0]


def test_note_sort_keys_of_different_materials_group_by_material():
    keys = [
        sort_keys.note_sort_key(
            material_id=material, chapter=chapter, page=1, note_id="n"
        )
        for material, chapter in (("b", "1"), ("a", "9"), ("b", "0"), ("a", "2"))
    ]

    assert sorted(keys) == [
        "a$$0000000002$$0000000001$$n",
        "a$$0000000009$$0000000001$$n",
        "b$$0000000000$$0000000001$$n",
        "b$$0000000001$$0000000001$$n",
    ]


@pytest.mark.parametrize(
    "make_key",
    [
        lambda moment: sort_keys.card_sort_key(added_at=moment, card_id=OTHER_ID),
        lambda moment: sort_keys.material_sort_key(added_at=moment, material_id=OTHER_ID),
    ],
    ids=["card", "material"],
)
def test_datetime_sort_keys_order_by_time(make_key):
    base = datetime.datetime(2024, 1, 1)
    moments = [
        base + datetime.timedelta(microseconds=999_999),
        base + datetime.timedelta(days=366),
        base + datetime.timedelta(microseconds=1),
        base - datetime.timedelta(microseconds=1),
        base + datetime.timedelta(microseconds=10),
        base,
    ]

    ordered = sorted(moments, key=make_key)

    assert ordered == sorted(moments)


def test_datetime_sort_keys_with_equal_time_order_by_id():
    moment = datetime.datetime(2024, 1, 1)

    first = sort_keys.card_sort_key(added_at=moment, card_id=MATERIAL_ID)
    second = sort_keys.card_sort_key(added_at=moment, card_id=OTHER_ID)

    assert first < second


def test_reading_log_sort_keys_order_by_date_within_material():
    dates = [
        datetime.date(2024, 12, 31),
        datetime.date(2024, 1, 2),
        datetime.date(2023, 12, 31),
        datetime.date(2024, 1, 10),
    ]

    ordered = sorted(
        dates,
        key=lambda date: sort_keys.reading_log_sort_key(
            material_id=MATERIAL_ID,
            date=date,
            log_id=OTHER_ID,
        ),
    )

    assert ordered == sorted(dates)
