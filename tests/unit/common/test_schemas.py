import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from tracker.common import schemas
from tracker.common.schemas import CustomBaseModel, MinMax, skip_empty_value


LOG_ID = UUID("018e9dbe-1d3d-7a5a-b437-9bfa65171b42")
MATERIAL_ID = UUID("1c2fc59d-5313-4615-9290-e8668abe2fc0")


class _Model(CustomBaseModel):
    title: str
    comment: str | None = None


def test_custom_base_model_forbids_extra_fields():
    with pytest.raises(ValidationError) as exc_info:
        _Model(title="t", unknown=1)

    assert [(e["type"], e["loc"]) for e in exc_info.value.errors()] == [
        ("extra_forbidden", ("unknown",)),
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  title  ", "title"),
        ("\n\tЗаголовок \r\n", "Заголовок"),
        ("in  ner", "in  ner"),
        ("   ", ""),
        ("", ""),
    ],
    ids=["spaces", "cyrillic-with-newlines", "inner-spaces-kept", "only-spaces", "empty"],
)
def test_custom_base_model_strips_whitespace_around_strings(raw, expected):
    assert _Model(title=raw).title == expected


def test_custom_base_model_strips_optional_strings():
    assert _Model(title="t", comment=" c ").comment == "c"


def test_custom_base_model_keeps_none():
    assert _Model(title="t").comment is None


def test_min_max_accepts_valid_values():
    result = MinMax(
        log_id=str(LOG_ID),
        material_id=MATERIAL_ID,
        material_title=" Title ",
        count=0,
        date="2024-02-29",
    )

    assert result.model_dump() == {
        "log_id": LOG_ID,
        "material_id": MATERIAL_ID,
        "material_title": "Title",
        "count": 0,
        "date": datetime.date(2024, 2, 29),
    }


def test_min_max_rejects_negative_count():
    with pytest.raises(ValidationError) as exc_info:
        MinMax(
            log_id=LOG_ID,
            material_id=MATERIAL_ID,
            material_title="t",
            count=-1,
            date=datetime.date(2024, 1, 1),
        )

    assert [e["loc"] for e in exc_info.value.errors()] == [("count",)]


def test_min_max_rejects_empty_ids():
    with pytest.raises(ValidationError) as exc_info:
        MinMax(
            log_id="",
            material_id="",
            material_title="t",
            count=1,
            date=datetime.date(2024, 1, 1),
        )

    assert sorted(e["loc"] for e in exc_info.value.errors()) == [
        ("log_id",),
        ("material_id",),
    ]


@pytest.mark.parametrize("value", ["", None], ids=["empty-string", "none"])
def test_skip_empty_value_turns_empty_into_none(value):
    assert skip_empty_value(value) is None


def test_skip_empty_value_keeps_uuid():
    assert skip_empty_value(LOG_ID) is LOG_ID


def test_skip_empty_value_keeps_nil_uuid():
    nil = UUID(int=0)

    assert schemas.skip_empty_value(nil) is nil
