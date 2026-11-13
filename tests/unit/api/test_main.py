import logging
import os
import subprocess
import sys

import orjson
import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request

from tests.conftest import TEST_ENVIRONMENT
from tests.unit.api import factories
from tracker import main
from tracker.common import database, kafka, manticoresearch
from tracker.notes import db as notes_db
from tracker.system import trends


NOTE_PATH = f"/api/v1/notes/{factories.NOTE_ID}"


def _request(path: str = "/api/v1/cards/") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "server": ("test", 80),
            "path": path,
            "query_string": b"",
            "headers": [],
        },
    )


def _body(response) -> dict:
    return orjson.loads(response.body)


@pytest.mark.parametrize(
    ("exc", "status_code", "detail"),
    [
        (
            database.InvalidNextTokenException("Invalid nextToken"),
            422,
            "InvalidNextToken: Invalid nextToken",
        ),
        (
            database.AlreadyExistsException("Card exists"),
            409,
            "AlreadyExistsError: Card exists",
        ),
        (
            database.NotFoundException("Note not found"),
            404,
            "NotFoundError: Note not found",
        ),
        (
            database.ConflictException("Material is not in the queue"),
            409,
            "ConflictError: Material is not in the queue",
        ),
        (database.NotFoundException(""), 404, "NotFoundError: "),
        (
            database.NotFoundException("Заметка не найдена"),
            404,
            "NotFoundError: Заметка не найдена",
        ),
    ],
    ids=[
        "invalid-token",
        "already-exists",
        "not-found",
        "conflict",
        "empty-message",
        "cyrillic",
    ],
)
async def test_client_database_error_is_mapped_to_its_status(
    client, mocker, tracker_log, exc, status_code, detail
):
    mocker.patch.object(notes_db, "count_links_to", mocker.AsyncMock(return_value=0))
    mocker.patch.object(notes_db, "delete_note", mocker.AsyncMock(side_effect=exc))

    response = await client.delete(NOTE_PATH)

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    assert tracker_log(logging.WARNING) == []


@pytest.mark.parametrize(
    "exc",
    [
        database.DatabaseException("connection lost"),
        trends.TrendException("connection lost"),
    ],
    ids=["base", "unmapped-subclass"],
)
async def test_other_database_error_is_500_and_logged_as_error(
    client, mocker, tracker_log, exc
):
    mocker.patch.object(notes_db, "count_links_to", mocker.AsyncMock(return_value=0))
    mocker.patch.object(notes_db, "delete_note", mocker.AsyncMock(side_effect=exc))

    response = await client.delete(NOTE_PATH)

    assert response.status_code == 500
    assert response.json() == {"detail": "Database error: connection lost"}
    errors = tracker_log(logging.ERROR)
    assert len(errors) == 1
    assert errors[0].getMessage() == (
        f"Database exception occurred, (http://test{NOTE_PATH}), connection lost"
    )


async def test_database_handler_called_directly_maps_conflict_to_409():
    response = await main.database_exception_handler(
        _request("/api/v1/materials/start"),
        database.ConflictException("Material is not in the queue"),
    )

    assert response.status_code == 409
    assert _body(response) == {"detail": "ConflictError: Material is not in the queue"}


async def test_unexpected_error_is_500(lenient_client, mocker):
    mocker.patch.object(
        notes_db, "delete_note", mocker.AsyncMock(side_effect=RuntimeError("boom"))
    )

    response = await lenient_client.delete(NOTE_PATH)

    assert response.status_code == 500
    assert "boom" not in response.text


async def test_kafka_error_is_503_and_logged_as_error(client, mocker, tracker_log):
    mocker.patch.object(notes_db, "get_note", mocker.AsyncMock())
    mocker.patch.object(
        kafka,
        "repeat_note",
        mocker.AsyncMock(side_effect=kafka.KafkaSendError("broker down")),
    )

    response = await client.post(f"{NOTE_PATH}/repeat-queue")

    assert response.status_code == 503
    assert response.json() == {"detail": "Kafka unavailable"}
    errors = tracker_log(logging.ERROR)
    assert len(errors) == 1
    assert "broker down" in errors[0].getMessage()


async def test_manticore_error_is_500_with_the_message(client, mocker, tracker_log):
    mocker.patch.object(
        manticoresearch,
        "autocompletion",
        mocker.AsyncMock(side_effect=manticoresearch.ManticoreException("no table")),
    )

    response = await client.get("/api/v1/notes/autocompletion", params={"query": "a"})

    assert response.status_code == 500
    assert response.json() == {"detail": "Manticoresearch error: no table"}
    assert len(tracker_log(logging.ERROR)) == 1


async def test_validation_error_is_flattened_to_one_string(client, tracker_log):
    response = await client.post("/api/v1/cards/", json={})

    assert response.status_code == 422
    assert response.json() == {
        "detail": (
            "body.material_id: Field required; "
            "body.note_id: Field required; "
            "body.question: Field required"
        ),
    }
    assert tracker_log(logging.WARNING) == []


async def test_validation_error_names_the_path_parameter(client):
    response = await client.delete("/api/v1/notes/not-a-uuid")

    assert response.status_code == 422
    assert response.json()["detail"].startswith(
        "path.note_id: Input should be a valid UUID"
    )


@pytest.mark.parametrize(
    ("errors", "expected"),
    [
        ([{"loc": ("query", "page_size"), "msg": "too big"}], "query.page_size: too big"),
        ([{"loc": ("body", "items", 0), "msg": "bad"}], "body.items.0: bad"),
        ([{}], ": "),
        ([{"loc": (), "msg": "a"}, {"loc": ("b",), "msg": ""}], ": a; b: "),
    ],
    ids=["one", "int-in-loc", "no-loc-no-msg", "two"],
)
def test_validation_detail_joins_location_and_message(errors, expected):
    assert main._validation_detail(RequestValidationError(errors)) == expected


def test_validation_detail_of_no_errors_is_the_repr():
    exc = RequestValidationError([])

    assert main._validation_detail(exc) == repr(exc)


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        ("Not found", "Not found"),
        ("", ""),
        ({"reason": "x"}, "{'reason': 'x'}"),
        (["a", 1], "['a', 1]"),
        (None, "Not Found"),
    ],
    ids=["str", "empty-str", "dict", "list", "default-phrase"],
)
def test_http_detail_is_always_a_string(detail, expected):
    assert main._http_detail(HTTPException(status_code=404, detail=detail)) == expected


@pytest.mark.parametrize("status_code", [400, 404, 499])
async def test_http_error_below_500_is_logged_as_info(tracker_log, status_code):
    response = await main.http_exception_handler(
        _request(), HTTPException(status_code=status_code, detail="nope")
    )

    assert response.status_code == status_code
    assert _body(response) == {"detail": "nope"}
    assert [r.levelno for r in tracker_log(logging.INFO)] == [logging.INFO]


@pytest.mark.parametrize("status_code", [500, 503])
async def test_http_error_from_500_is_logged_as_error(tracker_log, status_code):
    response = await main.http_exception_handler(
        _request(), HTTPException(status_code=status_code, detail={"why": "down"})
    )

    assert response.status_code == status_code
    assert _body(response) == {"detail": "{'why': 'down'}"}
    assert [r.levelno for r in tracker_log(logging.INFO)] == [logging.ERROR]


async def test_http_4xx_raised_by_a_route_is_not_logged_as_error(client, tracker_log):
    response = await client.post(
        "/api/v1/materials/parse/habr", json={"link": "https://example.com/post"}
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid habr url"}
    assert tracker_log(logging.ERROR) == []


async def test_starlette_405_bypasses_the_http_handler_current_behaviour(
    client, tracker_log
):
    response = await client.delete("/liveness")

    assert response.status_code == 405
    assert response.json() == {"detail": "Method Not Allowed"}
    assert [r for r in tracker_log() if "HTTP exception occurred" in r.getMessage()] == []


async def test_liveness(client):
    response = await client.get("/liveness")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    ("is_db_ready", "is_manticore_ready", "status_code"),
    [(True, True, 200), (True, False, 500), (False, True, 500), (False, False, 500)],
)
async def test_readiness_needs_both_probes(
    client, mocker, is_db_ready, is_manticore_ready, status_code
):
    mocker.patch.object(database, "readiness", mocker.AsyncMock(return_value=is_db_ready))
    mocker.patch.object(
        manticoresearch, "readiness", mocker.AsyncMock(return_value=is_manticore_ready)
    )

    response = await client.get("/readiness")

    assert response.status_code == status_code
    assert response.json() == {
        "is_db_ready": is_db_ready,
        "is_manticore_ready": is_manticore_ready,
    }


async def test_readiness_probe_that_raises_is_500_current_behaviour(
    lenient_client, mocker
):
    mocker.patch.object(
        database, "readiness", mocker.AsyncMock(side_effect=OSError("down"))
    )
    mocker.patch.object(manticoresearch, "readiness", mocker.AsyncMock(return_value=True))

    response = await lenient_client.get("/readiness")

    assert response.status_code == 500
    assert response.text == "Internal Server Error"


async def test_metrics_are_exposed(client):
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")


async def test_init_creates_the_database_before_the_search_index(mocker):
    calls = mocker.Mock()
    calls.attach_mock(
        mocker.patch.object(database, "create_db", mocker.AsyncMock()), "create_db"
    )
    calls.attach_mock(
        mocker.patch.object(manticoresearch, "init", mocker.AsyncMock()), "init"
    )

    await main.init()

    assert calls.mock_calls == [mocker.call.create_db(), mocker.call.init()]


async def test_init_stops_when_the_database_cannot_be_created(mocker):
    mocker.patch.object(
        database, "create_db", mocker.AsyncMock(side_effect=OSError("down"))
    )
    search_init = mocker.patch.object(manticoresearch, "init", mocker.AsyncMock())

    with pytest.raises(OSError, match="down"):
        await main.init()

    search_init.assert_not_awaited()


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/cards/",
        "/api/v1/materials/queue",
        "/api/v1/notes/search",
        "/api/v1/reading_logs/",
        "/api/v1/system/summary",
    ],
)
def test_every_router_is_mounted_under_api_v1(path):
    assert path in main.app.openapi()["paths"]


def test_service_routes_are_hidden_from_the_schema():
    paths = main.app.openapi()["paths"]

    assert not {"/liveness", "/readiness", "/metrics", "/{path}"} & paths.keys()


def test_metrics_are_labelled_with_the_hostname():
    script = (
        "from tracker.main import app\n"
        "labels = [m.kwargs['labels'] for m in app.user_middleware if 'labels' in m.kwargs]\n"
        "print(labels[0]['server_name'])\n"
    )
    env = {**TEST_ENVIRONMENT, "HOSTNAME": "tracker-pod-1", "PATH": os.environ["PATH"]}

    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )

    assert result.stdout.strip().splitlines()[-1] == "tracker-pod-1"
