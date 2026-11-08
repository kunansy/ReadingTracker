import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest

from tracker.cards import db as cards_db
from tracker.common import pagination
from tracker.main import app
from tracker.materials import db as materials_db
from tracker.notes import db as notes_db
from tracker.reading_log import db as reading_log_db


LISTINGS = [
    "/api/v1/cards/",
    "/api/v1/reading_logs/",
    "/api/v1/materials/queue",
    "/api/v1/materials/reading",
    "/api/v1/materials/completed",
    "/api/v1/materials/repeat",
    "/api/v1/notes/search",
]


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def no_side_queries(mocker):
    """Stub the queries a listing runs next to its page."""
    mocker.patch.object(materials_db, "get_means", mocker.AsyncMock(return_value={}))
    for name in (
        "get_distinct_chapters",
        "get_material_with_notes_titles",
        "get_material_types",
        "get_all_notes_count",
    ):
        mocker.patch.object(notes_db, name, mocker.AsyncMock(return_value={}))
    mocker.patch.object(notes_db, "get_sorted_tags", mocker.AsyncMock(return_value=[]))


def _empty_page() -> pagination.Page:
    return pagination.Page(items=[], next_token=None, total_count=0)


@pytest.mark.parametrize("path", LISTINGS)
@pytest.mark.parametrize("page_size", [0, pagination.MAX_PAGE_SIZE + 1])
async def test_page_size_out_of_bounds_is_rejected(client, path, page_size):
    response = await client.get(path, params={"page_size": page_size})

    assert response.status_code == 422
    assert "page_size" in response.json()["detail"]


TASK_GROUP_LISTINGS = {"/api/v1/materials/queue", "/api/v1/notes/search"}


@pytest.mark.parametrize(
    "path",
    [
        pytest.param(
            path,
            marks=pytest.mark.xfail(
                strict=True,
                reason="TaskGroup wraps the token error in an ExceptionGroup, giving 500",
            ),
        )
        if path in TASK_GROUP_LISTINGS
        else path
        for path in LISTINGS
    ],
)
async def test_malformed_next_token_is_rejected(client, no_side_queries, path):
    response = await client.get(path, params={"next_token": "garbage"})

    assert response.status_code == 422
    assert response.json()["detail"].startswith("InvalidNextToken:")


async def test_cards_material_filter_reaches_db(client, mocker):
    get_page = mocker.patch.object(
        cards_db,
        "get_cards_page",
        mocker.AsyncMock(return_value=_empty_page()),
    )
    material_id = uuid.uuid4()

    response = await client.get(
        "/api/v1/cards/",
        params={"material_id": str(material_id)},
    )

    assert response.status_code == 200
    assert get_page.await_args.kwargs["material_id"] == material_id


async def test_reading_logs_material_filter_reaches_db(client, mocker):
    get_page = mocker.patch.object(
        reading_log_db,
        "list_log_records_page",
        mocker.AsyncMock(return_value=_empty_page()),
    )
    material_id = uuid.uuid4()

    response = await client.get(
        "/api/v1/reading_logs/",
        params={"material_id": str(material_id)},
    )

    assert response.status_code == 200
    assert get_page.await_args.kwargs["material_id"] == material_id


async def test_repeat_outlined_filter_reaches_db(client, mocker):
    get_page = mocker.patch.object(
        materials_db,
        "get_repeating_queue_page",
        mocker.AsyncMock(return_value=_empty_page()),
    )

    response = await client.get(
        "/api/v1/materials/repeat",
        params={"only_outlined": "true"},
    )

    assert response.status_code == 200
    assert get_page.await_args.kwargs["is_outlined"] is True


async def test_completed_filters_reach_db(client, mocker):
    get_page = mocker.patch.object(
        materials_db,
        "completed_statistics_page",
        mocker.AsyncMock(return_value=_empty_page()),
    )

    response = await client.get(
        "/api/v1/materials/completed",
        params={"material_type": "book", "outlined": "outlined", "tags_query": "a b"},
    )

    assert response.status_code == 200
    kwargs = get_page.await_args.kwargs
    assert kwargs["material_type"] == "book"
    assert kwargs["is_outlined"] is True
    assert kwargs["tags"] == {"a", "b"}


async def test_page_params_reach_db(client, mocker):
    get_page = mocker.patch.object(
        cards_db,
        "get_cards_page",
        mocker.AsyncMock(return_value=_empty_page()),
    )

    response = await client.get(
        "/api/v1/cards/",
        params={"page_size": 7, "order": "asc", "next_token": "token"},
    )

    assert response.status_code == 200
    params = get_page.await_args.kwargs["params"]
    assert params.page_size == 7
    assert params.order == pagination.Order.ASC
    assert params.next_token == "token"


async def test_notes_search_filters_reach_db(client, no_side_queries, mocker):
    search_page = mocker.patch.object(
        notes_db,
        "search_notes_page",
        mocker.AsyncMock(return_value=_empty_page()),
    )
    material_id = uuid.uuid4()

    response = await client.get(
        "/api/v1/notes/search",
        params={"material_id": str(material_id), "tags_query": "x y"},
    )

    assert response.status_code == 200
    kwargs = search_page.await_args.kwargs
    assert str(kwargs["material_id"]) == str(material_id)
    assert kwargs["tags"] == {"x", "y"}
    assert kwargs["note_ids"] is None
