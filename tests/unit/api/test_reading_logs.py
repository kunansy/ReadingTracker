import datetime

import pytest

from tests.unit.api import factories
from tracker.common import database, pagination
from tracker.reading_log import db as reading_log_db


URL = "/api/v1/reading_logs/"


@pytest.fixture
def list_page(mocker):
    return mocker.patch.object(
        reading_log_db,
        "list_log_records_page",
        mocker.AsyncMock(return_value=factories.page()),
    )


async def test_list_logs_returns_an_empty_page(client, list_page):
    response = await client.get(URL)

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_token": None, "total_count": 0}
    list_page.assert_awaited_once_with(material_id=None, params=pagination.PageParams())


async def test_list_logs_serializes_the_page(client, list_page):
    list_page.return_value = pagination.Page(
        items=[factories.log_record()], next_token="next", total_count=2
    )

    response = await client.get(URL)

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "log_id": str(factories.LOG_ID),
                "material_id": str(factories.MATERIAL_ID),
                "count": 90,
                "date": "2026-01-15",
            },
        ],
        "next_token": "next",
        "total_count": 2,
    }


async def test_list_logs_passes_filter_and_page_params(client, list_page):
    response = await client.get(
        URL,
        params={
            "material_id": str(factories.MATERIAL_ID),
            "page_size": 100,
            "order": "desc",
            "next_token": "t",
        },
    )

    assert response.status_code == 200
    list_page.assert_awaited_once_with(
        material_id=factories.MATERIAL_ID,
        params=pagination.PageParams(
            page_size=100, order=pagination.Order.DESC, next_token="t"
        ),
    )


@pytest.mark.parametrize(
    "params",
    [
        {"page_size": 0},
        {"page_size": 101},
        {"next_token": "a" * (pagination.MAX_TOKEN_LENGTH + 1)},
        {"material_id": "bad"},
    ],
    ids=["page-size-zero", "page-size-over-max", "token-too-long", "bad-uuid"],
)
async def test_list_logs_rejects_invalid_query(client, list_page, params):
    response = await client.get(URL, params=params)

    assert response.status_code == 422
    list_page.assert_not_awaited()


async def test_list_logs_maps_invalid_token_to_422(client, list_page):
    list_page.side_effect = database.InvalidNextTokenException("next_token is malformed")

    response = await client.get(URL, params={"next_token": "garbage"})

    assert response.status_code == 422
    assert response.json() == {"detail": "InvalidNextToken: next_token is malformed"}


@pytest.fixture
def log_db(mocker):
    return {
        "check": mocker.patch.object(
            reading_log_db, "check_record_correct", mocker.AsyncMock()
        ),
        "insert": mocker.patch.object(
            reading_log_db,
            "insert_log_record",
            mocker.AsyncMock(return_value=factories.LOG_ID),
        ),
    }


def _body(**patch) -> dict:
    return {
        "material_id": str(factories.MATERIAL_ID),
        "count": 1,
        "date": "2026-03-10",
        **patch,
    }


async def test_create_log_record_checks_then_inserts(client, log_db):
    response = await client.post(URL, json=_body())

    assert response.status_code == 201
    assert response.json() == {"log_id": str(factories.LOG_ID)}
    expected = {
        "material_id": factories.MATERIAL_ID,
        "date": datetime.date(2026, 3, 10),
        "count": 1,
    }
    log_db["check"].assert_awaited_once_with(**expected)
    log_db["insert"].assert_awaited_once_with(**expected)


async def test_create_log_record_maps_a_failed_check_to_400(client, log_db):
    log_db["check"].side_effect = ValueError("The date even exists")

    response = await client.post(URL, json=_body())

    assert response.status_code == 400
    assert response.json() == {"detail": "The date even exists"}
    log_db["insert"].assert_not_awaited()


async def test_create_log_record_maps_a_missing_material_to_404(client, log_db):
    log_db["check"].side_effect = database.NotFoundException("Material not found")

    response = await client.post(URL, json=_body())

    assert response.status_code == 404
    assert response.json() == {"detail": "NotFoundError: Material not found"}
    log_db["insert"].assert_not_awaited()


async def test_create_log_record_maps_a_duplicate_to_409(client, log_db):
    log_db["insert"].side_effect = database.AlreadyExistsException("Record exists")

    response = await client.post(URL, json=_body())

    assert response.status_code == 409
    assert response.json() == {"detail": "AlreadyExistsError: Record exists"}


@pytest.mark.parametrize(
    ("patch", "detail"),
    [
        ({"count": 0}, "body.count: Input should be greater than 0"),
        ({"count": -5}, "body.count: Input should be greater than 0"),
        ({"count": 1.5}, "body.count: Input should be a valid integer"),
        ({"date": "10.03.2026"}, "body.date: Input should be a valid date"),
        ({"date": "2026-02-30"}, "body.date: Input should be a valid date"),
        ({"material_id": "x"}, "body.material_id: Input should be a valid UUID"),
        ({"extra": 1}, "body.extra: Extra inputs are not permitted"),
    ],
    ids=[
        "zero",
        "negative",
        "fractional",
        "bad-format",
        "no-such-day",
        "bad-uuid",
        "extra",
    ],
)
async def test_create_log_record_rejects_invalid_body(client, log_db, patch, detail):
    response = await client.post(URL, json=_body(**patch))

    assert response.status_code == 422
    assert response.json()["detail"].startswith(detail)
    log_db["check"].assert_not_awaited()
    log_db["insert"].assert_not_awaited()


async def test_create_log_record_requires_every_field(client, log_db):
    response = await client.post(URL, json={})

    assert response.status_code == 422
    assert response.json() == {
        "detail": (
            "body.material_id: Field required; "
            "body.count: Field required; "
            "body.date: Field required"
        ),
    }


@pytest.mark.parametrize(
    ("material_id", "expected"),
    [(None, None), (factories.MATERIAL_ID, str(factories.MATERIAL_ID))],
    ids=["nothing-is-read", "reading"],
)
async def test_material_reading_now(client, mocker, material_id, expected):
    mocker.patch.object(
        reading_log_db,
        "get_material_reading_now",
        mocker.AsyncMock(return_value=material_id),
    )

    response = await client.get("/api/v1/reading_logs/material-reading-now")

    assert response.status_code == 200
    assert response.json() == {"material_id": expected}
