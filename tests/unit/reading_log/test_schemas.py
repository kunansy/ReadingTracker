import datetime

import pytest
from pydantic import ValidationError

from tests.unit.materials.helpers import uid
from tracker.reading_log import db, schemas


def _request(**overrides):
    return {"material_id": str(uid(1)), "count": 1, "date": "2024-03-10"} | overrides


def _item(**overrides):
    return {"log_id": str(uid(2)), **_request()} | overrides


@pytest.mark.parametrize("count", [1, 2, 10**6], ids=["minimum", "two", "large"])
def test_create_request_accepts_positive_count(count):
    request = schemas.CreateReadingLogsRequest(**_request(count=count))

    assert request.count == count
    assert request.material_id == uid(1)
    assert request.date == datetime.date(2024, 3, 10)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("count", 0),
        ("count", -1),
        ("count", 1.5),
        ("count", "ten"),
        ("count", None),
        ("material_id", "not-a-uuid"),
        ("material_id", ""),
        ("material_id", None),
        ("date", "2023-02-29"),
        ("date", "10.03.2024"),
        ("date", "2024-03-10T08:00:00"),
        ("date", None),
        ("log_id", str(uid(2))),
    ],
    ids=lambda value: f"{value!r}",
)
def test_create_request_rejects_invalid_field(field, value):
    with pytest.raises(ValidationError) as exc_info:
        schemas.CreateReadingLogsRequest(**_request(**{field: value}))

    assert exc_info.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize("field", ["material_id", "count", "date"])
def test_create_request_requires_field(field):
    payload = _request()
    del payload[field]

    with pytest.raises(ValidationError) as exc_info:
        schemas.CreateReadingLogsRequest(**payload)

    assert [(e["loc"], e["type"]) for e in exc_info.value.errors()] == [((field,), "missing")]


def test_create_request_accepts_future_date():
    """The future-date rule lives in `check_record_correct`, not in the schema."""
    request = schemas.CreateReadingLogsRequest(**_request(date="2999-12-31"))

    assert request.date == datetime.date(2999, 12, 31)


def test_list_item_accepts_zero_count():
    assert schemas._ListLogRecordItem(**_item(count=0)).count == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [("count", -1), ("log_id", None), ("log_id", "x"), ("material_id", "x"), ("date", "x")],
    ids=lambda value: f"{value!r}",
)
def test_list_item_rejects_invalid_field(field, value):
    with pytest.raises(ValidationError) as exc_info:
        schemas._ListLogRecordItem(**_item(**{field: value}))

    assert exc_info.value.errors()[0]["loc"] == (field,)


def test_list_response_requires_pagination_fields():
    response = schemas.ListReadingLogsResponse(
        next_token=None,
        total_count=1,
        items=[_item()],
    )

    assert response.items[0].log_id == uid(2)
    with pytest.raises(ValidationError):
        schemas.ListReadingLogsResponse(items=[])
    with pytest.raises(ValidationError):
        schemas.ListReadingLogsResponse(next_token=None, total_count=1, items=[_item(count=-1)])


def test_single_record_responses():
    assert schemas.CreateReadingLogsResponse(log_id=str(uid(2))).log_id == uid(2)
    assert schemas.GetReadingLogResponse(reading_log=_item()).reading_log.count == 1

    with pytest.raises(ValidationError):
        schemas.CreateReadingLogsResponse(log_id=None)


def test_material_reading_now_is_nullable_but_required():
    assert schemas.GetMaterialReadingNowResponse(material_id=None).material_id is None
    assert schemas.GetMaterialReadingNowResponse(material_id=str(uid(1))).material_id == uid(1)

    with pytest.raises(ValidationError):
        schemas.GetMaterialReadingNowResponse()


def test_log_record_defaults_and_required_material():
    record = db.LogRecord(material_id=uid(1), count=0, date=datetime.date(2024, 3, 10))

    assert record.log_id is None
    assert record.material_title is None
    with pytest.raises(ValidationError):
        db.LogRecord(material_id=None, count=0, date=datetime.date(2024, 3, 10))


def test_log_record_from_a_row_with_extra_columns_is_rejected():
    """`extra="forbid"` applies to mappings only; rows are read with from_attributes."""
    with pytest.raises(ValidationError):
        db.LogRecord(**_item(sort_key="k"))
