import datetime
import uuid
from collections import defaultdict
from collections.abc import AsyncGenerator
from decimal import Decimal

import httpx
import pytest

from tracker.cards import db as cards_db
from tracker.common import pagination
from tracker.main import app
from tracker.materials import db as materials_db
from tracker.models import enums
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


def _note(material_id: uuid.UUID, **fields) -> notes_db.Note:
    return notes_db.Note(
        note_id=uuid.uuid4(),
        material_id=material_id,
        content="content #tag",
        added_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        chapter="1",
        page=10,
        tags={"tag"},
        is_deleted=False,
        note_number=1,
        **fields,
    )


async def test_notes_search_serializes_a_non_empty_page(client, mocker):
    material_id = uuid.uuid4()
    titled = _note(material_id, title="title", links_count=2)
    untitled = _note(material_id)
    mocker.patch.object(
        notes_db,
        "search_notes_page",
        mocker.AsyncMock(
            return_value=pagination.Page(
                items=[titled, untitled], next_token=None, total_count=2
            ),
        ),
    )
    chapters: defaultdict[uuid.UUID, list[str]] = defaultdict(list)
    chapters[material_id].append("1")
    side_queries = {
        "get_distinct_chapters": chapters,
        "get_material_with_notes_titles": {material_id: "Material"},
        "get_material_types": {material_id: enums.MaterialTypesEnum.book},
        "get_all_notes_count": {material_id: 2},
        "get_sorted_tags": ["tag"],
    }
    for name, value in side_queries.items():
        mocker.patch.object(notes_db, name, mocker.AsyncMock(return_value=value))

    response = await client.get(
        "/api/v1/notes/search", params={"material_id": str(material_id)}
    )

    assert response.status_code == 200
    body = response.json()
    key = str(material_id)
    assert body["material_id"] == key
    assert body["titles"] == {key: "Material"}
    assert body["material_types"] == {key: "book"}
    assert body["material_notes"] == {key: 2}
    assert body["chapters"] == {key: ["1"]}
    assert body["tags"] == ["tag"]
    assert [n["note_id"] for n in body["notes"]] == [
        str(titled.note_id),
        str(untitled.note_id),
    ]
    assert body["notes"][0]["title"] == "title"
    assert body["notes"][0]["links_count"] == 2
    assert body["notes"][1]["title"] is None
    assert body["notes"][1]["links_count"] is None
    assert all(n["is_deleted"] is False for n in body["notes"])


async def test_notes_search_rejects_a_malformed_material_id(client, no_side_queries):
    response = await client.get(
        "/api/v1/notes/search", params={"material_id": "not-a-uuid"}
    )

    assert response.status_code == 422


@pytest.fixture
def graph_queries(mocker):
    material_id = uuid.uuid4()
    note = _note(material_id)
    get_notes = mocker.patch.object(
        notes_db, "get_notes", mocker.AsyncMock(return_value=[note])
    )
    mocker.patch.object(
        notes_db,
        "get_material_titles",
        mocker.AsyncMock(return_value={material_id: "Material"}),
    )
    mocker.patch.object(notes_db, "create_graphic", return_value="<html></html>")
    return material_id, get_notes


async def test_notes_graph_for_all_notes(client, graph_queries, mocker):
    material_id, _ = graph_queries
    link_all = mocker.spy(notes_db, "link_all_notes")

    response = await client.get("/api/v1/notes/graph")

    assert response.status_code == 200
    assert response.json() == {
        "iframe_srcdoc": "<html></html>",
        "titles": {str(material_id): "Material"},
        "material_id": None,
    }
    link_all.assert_called_once()


async def test_notes_graph_for_one_material(client, graph_queries, mocker):
    material_id, get_notes = graph_queries
    material_graph = mocker.spy(notes_db, "create_material_graph")

    response = await client.get(
        "/api/v1/notes/graph", params={"material_id": str(material_id)}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["material_id"] == str(material_id)
    assert body["titles"] == {str(material_id): "Material"}
    material_graph.assert_called_once()
    get_notes.assert_any_await(material_id=material_id)


async def test_materials_queue_mean_is_a_json_number(client, mocker):
    mocker.patch.object(
        materials_db, "estimate_page", mocker.AsyncMock(return_value=_empty_page())
    )
    mocker.patch.object(
        materials_db,
        "get_means",
        mocker.AsyncMock(return_value={enums.MaterialTypesEnum.book: Decimal("1.50")}),
    )

    response = await client.get("/api/v1/materials/queue")

    assert response.status_code == 200
    assert response.json()["mean"] == {"book": 1.5}
