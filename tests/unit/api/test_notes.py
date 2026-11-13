import datetime
from uuid import UUID

import pytest

from tests.unit.api import factories
from tracker.common import database, kafka, manticoresearch, pagination
from tracker.materials import db as materials_db
from tracker.models import enums
from tracker.notes import db as notes_db
from tracker.notes.schemas import MAX_SEARCH_QUERY_LENGTH


BASE = "/api/v1/notes"
NOTE_URL = f"{BASE}/{factories.NOTE_ID}"
NOW = datetime.datetime(2026, 3, 10, 12, 30, 0)
NOT_FOUND = database.NotFoundException("Note not found")
NOT_FOUND_BODY = {"detail": "NotFoundError: Note not found"}
TASK_GROUP_BUG = (
    "BUG: {where} an error raised inside asyncio.TaskGroup reaches the app as "
    "ExceptionGroup, so the registered exception handler is bypassed: {effect}"
)


def _patch(mocker, name: str, **kwargs):
    return mocker.patch.object(notes_db, name, mocker.AsyncMock(**kwargs))


@pytest.fixture
def search_db(mocker):
    side_queries = {
        "get_distinct_chapters": {},
        "get_material_with_notes_titles": {},
        "get_material_types": {},
        "get_all_notes_count": {},
        "get_sorted_tags": [],
    }
    mocks = {
        name: _patch(mocker, name, return_value=value)
        for name, value in side_queries.items()
    }
    mocks["search_notes_page"] = _patch(
        mocker, "search_notes_page", return_value=factories.page()
    )
    mocks["search"] = mocker.patch.object(
        manticoresearch, "search", mocker.AsyncMock(return_value={})
    )
    return mocks


async def test_search_without_filters_returns_an_empty_page(client, search_db):
    response = await client.get(f"{BASE}/search")

    assert response.status_code == 200
    assert response.json() == {
        "notes": [],
        "total_count": 0,
        "titles": {},
        "material_types": {},
        "material_notes": {},
        "chapters": {},
        "query": None,
        "tags": [],
        "tags_query": None,
        "next_token": None,
        "page_size": 20,
        "material_id": None,
    }
    search_db["search"].assert_not_awaited()
    search_db["search_notes_page"].assert_awaited_once_with(
        material_id=None,
        query=None,
        tags=set(),
        note_ids=None,
        params=pagination.PageParams(),
    )


async def test_search_serializes_notes_and_side_data(client, search_db):
    linked = factories.note(
        title="Заголовок",
        link_id=factories.OTHER_NOTE_ID,
        links_count=2,
        tags={"tag", "тег"},
        chapter="1.2",
        is_deleted=True,
    )
    plain = factories.note(
        note_id=factories.OTHER_NOTE_ID, content="plain", tags=set(), chapter="", page=0
    )
    search_db["search_notes_page"].return_value = pagination.Page(
        items=[linked, plain], next_token="next", total_count=22
    )
    search_db["get_distinct_chapters"].return_value = {factories.MATERIAL_ID: ["", "1.2"]}
    search_db["get_material_with_notes_titles"].return_value = {
        factories.MATERIAL_ID: "Война и мир"
    }
    search_db["get_material_types"].return_value = {
        factories.MATERIAL_ID: enums.MaterialTypesEnum.book
    }
    search_db["get_all_notes_count"].return_value = {factories.MATERIAL_ID: 22}
    search_db["get_sorted_tags"].return_value = ["tag", "тег"]

    response = await client.get(
        f"{BASE}/search",
        params={
            "material_id": str(factories.MATERIAL_ID),
            "tags_query": "тег tag",
            "page_size": 2,
        },
    )

    assert response.status_code == 200
    key = str(factories.MATERIAL_ID)
    assert response.json() == {
        "notes": [
            {
                "note_id": str(factories.NOTE_ID),
                "material_id": key,
                "title": "Заголовок",
                "content_html": "Content #tag",
                "tags_html": (
                    '<a href=http://tracker.test/notes/?tags_query=tag target="_blank">'
                    "#tag</a> "
                    '<a href=http://tracker.test/notes/?tags_query=тег target="_blank">'
                    "#тег</a>"
                ),
                "link_html": (
                    '<a class="link-ref" '
                    f"href=http://tracker.test/notes/{factories.OTHER_NOTE_ID} "
                    f'target="_blank">[[{factories.OTHER_NOTE_ID}]]</a>'
                ),
                "chapter": "1.2",
                "chapter_int": 12,
                "page": 10,
                "links_count": 2,
                "is_deleted": True,
            },
            {
                "note_id": str(factories.OTHER_NOTE_ID),
                "material_id": key,
                "title": None,
                "content_html": "plain",
                "tags_html": "",
                "link_html": "",
                "chapter": "",
                "chapter_int": 0,
                "page": 0,
                "links_count": None,
                "is_deleted": False,
            },
        ],
        "total_count": 22,
        "titles": {key: "Война и мир"},
        "material_types": {key: "book"},
        "material_notes": {key: 22},
        "chapters": {key: ["", "1.2"]},
        "query": None,
        "tags": ["tag", "тег"],
        "tags_query": "тег tag",
        "next_token": "next",
        "page_size": 2,
        "material_id": key,
    }
    search_db["search_notes_page"].assert_awaited_once_with(
        material_id=factories.MATERIAL_ID,
        query=None,
        tags={"tag", "тег"},
        note_ids=None,
        params=pagination.PageParams(page_size=2),
    )
    search_db["get_sorted_tags"].assert_awaited_once_with(
        material_id=factories.MATERIAL_ID
    )


async def test_search_with_query_highlights_the_found_notes(client, search_db):
    search_db["search"].return_value = {
        factories.NOTE_ID: manticoresearch.SearchResult(
            replace_substring="мир", snippet="<b>мир</b>"
        ),
    }
    search_db["search_notes_page"].return_value = factories.page(
        [factories.note(content="Война и мир")]
    )

    response = await client.get(f"{BASE}/search", params={"query": "мир"})

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "мир"
    assert [n["content_html"] for n in body["notes"]] == ["Война и <b>мир</b>"]
    search_db["search"].assert_awaited_once_with("мир")
    kwargs = search_db["search_notes_page"].await_args.kwargs
    assert kwargs["query"] == "мир"
    assert list(kwargs["note_ids"]) == [factories.NOTE_ID]


@pytest.mark.parametrize("param", ["query", "tags_query"])
async def test_search_accepts_a_query_of_max_length(client, search_db, param):
    response = await client.get(
        f"{BASE}/search", params={param: "a" * MAX_SEARCH_QUERY_LENGTH}
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("params", "location"),
    [
        ({"query": "a" * (MAX_SEARCH_QUERY_LENGTH + 1)}, "query.query"),
        ({"tags_query": "a" * (MAX_SEARCH_QUERY_LENGTH + 1)}, "query.tags_query"),
        ({"material_id": "not-a-uuid"}, "query.material_id"),
        ({"material_id": ""}, "query.material_id"),
        ({"page_size": 0}, "query.page_size"),
        ({"page_size": 101}, "query.page_size"),
        ({"next_token": "a" * (pagination.MAX_TOKEN_LENGTH + 1)}, "query.next_token"),
    ],
    ids=[
        "query-too-long",
        "tags-query-too-long",
        "bad-uuid",
        "empty-uuid",
        "page-size-zero",
        "page-size-over-max",
        "token-too-long",
    ],
)
async def test_search_rejects_invalid_query(client, search_db, params, location):
    response = await client.get(f"{BASE}/search", params=params)

    assert response.status_code == 422
    assert response.json()["detail"].startswith(f"{location}: ")
    search_db["search_notes_page"].assert_not_awaited()


@pytest.mark.xfail(
    strict=True,
    reason=TASK_GROUP_BUG.format(
        where="tracker/notes/listing.py:31",
        effect="a malformed next_token on /notes/search is 500 instead of 422",
    ),
)
async def test_search_maps_invalid_token_to_422(lenient_client, search_db):
    search_db["search_notes_page"].side_effect = database.InvalidNextTokenException(
        "next_token is malformed"
    )

    response = await lenient_client.get(
        f"{BASE}/search", params={"next_token": "garbage"}
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "InvalidNextToken: next_token is malformed"}


async def test_search_maps_a_search_engine_failure_to_500(client, search_db):
    search_db["search"].side_effect = manticoresearch.ManticoreException("down")

    response = await client.get(f"{BASE}/search", params={"query": "a"})

    assert response.status_code == 500
    assert response.json() == {"detail": "Manticoresearch error: down"}


OTHER_MATERIAL_NOTE_ID = UUID("99999999-9999-4999-8999-999999999999")


@pytest.fixture
def graph_db(mocker):
    root = factories.note(content="root")
    child = factories.note(
        note_id=factories.OTHER_NOTE_ID, link_id=root.note_id, content="child"
    )
    foreign = factories.note(
        note_id=OTHER_MATERIAL_NOTE_ID,
        material_id=factories.OTHER_MATERIAL_ID,
        link_id=root.note_id,
        content="foreign",
    )
    all_notes = [root, child, foreign]

    async def get_notes(*, material_id=None):
        return [n for n in all_notes if material_id in (None, n.material_id)]

    return {
        "get_notes": _patch(mocker, "get_notes", side_effect=get_notes),
        "get_material_titles": _patch(
            mocker,
            "get_material_titles",
            return_value={factories.MATERIAL_ID: "Война и мир"},
        ),
        "create_graphic": mocker.patch.object(
            notes_db, "create_graphic", mocker.Mock(return_value="<html>graph</html>")
        ),
    }


def _drawn_graph(graph_db):
    (graph,), kwargs = graph_db["create_graphic"].call_args
    return graph, kwargs


async def test_graph_of_all_notes(client, graph_db):
    response = await client.get(f"{BASE}/graph")

    assert response.status_code == 200
    assert response.json() == {
        "iframe_srcdoc": "<html>graph</html>",
        "titles": {str(factories.MATERIAL_ID): "Война и мир"},
        "material_id": None,
    }
    graph_db["get_notes"].assert_awaited_once_with()
    graph, kwargs = _drawn_graph(graph_db)
    assert kwargs == {"height": "80vh"}
    assert set(graph.nodes) == {
        str(factories.NOTE_ID),
        str(factories.OTHER_NOTE_ID),
        str(OTHER_MATERIAL_NOTE_ID),
    }
    assert set(graph.edges) == {
        (str(factories.OTHER_NOTE_ID), str(factories.NOTE_ID)),
        (str(OTHER_MATERIAL_NOTE_ID), str(factories.NOTE_ID)),
    }


async def test_graph_without_notes_is_empty(client, graph_db):
    graph_db["get_notes"].side_effect = None
    graph_db["get_notes"].return_value = []
    graph_db["get_material_titles"].return_value = {}

    response = await client.get(f"{BASE}/graph")

    assert response.status_code == 200
    assert response.json() == {
        "iframe_srcdoc": "<html>graph</html>",
        "titles": {},
        "material_id": None,
    }
    graph, _ = _drawn_graph(graph_db)
    assert len(graph.nodes) == 0


async def test_graph_of_one_material_marks_foreign_notes(client, graph_db, mocker):
    response = await client.get(
        f"{BASE}/graph", params={"material_id": str(factories.MATERIAL_ID)}
    )

    assert response.status_code == 200
    assert response.json() == {
        "iframe_srcdoc": "<html>graph</html>",
        "titles": {str(factories.MATERIAL_ID): "Война и мир"},
        "material_id": str(factories.MATERIAL_ID),
    }
    assert graph_db["get_notes"].await_args_list == [
        mocker.call(),
        mocker.call(material_id=factories.MATERIAL_ID),
    ]
    graph, kwargs = _drawn_graph(graph_db)
    assert kwargs == {"height": "80vh"}
    assert len(graph.nodes) == 3
    assert graph.nodes[str(OTHER_MATERIAL_NOTE_ID)]["color"] == "black"
    assert graph.nodes[str(factories.NOTE_ID)].get("color") is None


async def test_graph_of_a_material_without_notes_is_empty(lenient_client, graph_db):
    response = await lenient_client.get(
        f"{BASE}/graph", params={"material_id": str(UUID(int=1))}
    )

    assert response.status_code == 200
    assert response.json()["material_id"] == str(UUID(int=1))


async def test_graph_rejects_bad_uuid(client, graph_db):
    response = await client.get(f"{BASE}/graph", params={"material_id": "x"})

    assert response.status_code == 422
    graph_db["get_notes"].assert_not_awaited()


@pytest.mark.xfail(
    strict=True,
    reason=TASK_GROUP_BUG.format(
        where="tracker/api/v1/notes.py:51,88",
        effect="a database failure answers a bare 500 instead of the JSON error body",
    ),
)
@pytest.mark.parametrize("path", ["graph", "meta"])
async def test_task_group_listing_reports_a_database_failure_as_json(
    lenient_client, graph_db, mocker, path
):
    _patch(mocker, "get_sorted_tags", return_value=[])
    graph_db["get_material_titles"].side_effect = database.DatabaseException(
        "connection lost"
    )

    response = await lenient_client.get(f"{BASE}/{path}")

    assert response.status_code == 500
    assert response.text == '{"detail":"Database error: connection lost"}'


@pytest.mark.parametrize(
    ("params", "material_id"),
    [({}, None), ({"material_id": str(factories.MATERIAL_ID)}, factories.MATERIAL_ID)],
    ids=["all", "one-material"],
)
async def test_meta(client, mocker, params, material_id):
    get_titles = _patch(
        mocker, "get_material_titles", return_value={factories.MATERIAL_ID: "Война и мир"}
    )
    get_tags = _patch(mocker, "get_sorted_tags", return_value=["b", "a"])

    response = await client.get(f"{BASE}/meta", params=params)

    assert response.status_code == 200
    assert response.json() == {
        "titles": {str(factories.MATERIAL_ID): "Война и мир"},
        "tags": ["b", "a"],
    }
    get_titles.assert_awaited_once_with()
    get_tags.assert_awaited_once_with(material_id=material_id)


@pytest.fixture
def write_db(mocker):
    mocker.patch.object(database, "utcnow", return_value=NOW)
    return {
        "get_material": mocker.patch.object(
            materials_db,
            "get_material_api",
            mocker.AsyncMock(return_value=factories.material()),
        ),
        "get_link": _patch(
            mocker,
            "get_note",
            return_value=factories.note(note_id=factories.OTHER_NOTE_ID),
        ),
        "is_link_cyclic": _patch(mocker, "is_link_cyclic", return_value=False),
        "insert_note": _patch(mocker, "insert_note", return_value=factories.NOTE_ID),
        "update_note": _patch(mocker, "update_note", return_value=None),
        "index_insert": mocker.patch.object(
            manticoresearch, "insert_note", mocker.AsyncMock()
        ),
        "index_update": mocker.patch.object(
            manticoresearch, "update_content", mocker.AsyncMock()
        ),
    }


async def test_add_note_with_required_fields_only(client, write_db):
    response = await client.post(
        f"{BASE}/add",
        json={"material_id": str(factories.MATERIAL_ID), "content": "Заметка."},
    )

    assert response.status_code == 201
    assert response.json() == {"note_id": str(factories.NOTE_ID)}
    write_db["insert_note"].assert_awaited_once_with(
        material_id=factories.MATERIAL_ID,
        link_id=None,
        title=None,
        content="Заметка.",
        chapter="",
        page=0,
        tags=[],
    )
    write_db["index_insert"].assert_awaited_once_with(
        note_id=factories.NOTE_ID, content="Заметка.", added_at=NOW
    )


async def test_add_note_formats_content_and_normalizes_tags(client, write_db):
    response = await client.post(
        f"{BASE}/add",
        json={
            "material_id": str(factories.MATERIAL_ID),
            "content": 'он сказал  "да" -- и x^2 ушёл',
            "title": " Title ",
            "tags": ["Beta", "alpha"],
            "link_id": str(factories.OTHER_NOTE_ID),
            "chapter": "1.2",
            "page": 15,
        },
    )

    assert response.status_code == 201
    content = "Он сказал «да» — и x<sup>2</sup> ушёл"
    write_db["insert_note"].assert_awaited_once_with(
        material_id=factories.MATERIAL_ID,
        link_id=factories.OTHER_NOTE_ID,
        title="Title",
        content=content,
        chapter="1.2",
        page=15,
        tags=["alpha", "beta"],
    )
    assert write_db["index_insert"].await_args.kwargs["content"] == content


@pytest.mark.parametrize(
    ("patch", "detail"),
    [
        ({"content": None}, "body.content: "),
        ({"page": -1}, "body.page: Input should be greater than or equal to 0"),
        ({"tags": ["two words"]}, "body.tags.0: String should match pattern"),
        ({"tags": "tag"}, "body.tags: Input should be a valid list"),
        ({"link_id": "x"}, "body.link_id: Input should be a valid UUID"),
        ({"chapter": "c" * 300}, "body.chapter: String should have at most"),
        (
            {"note_id": str(factories.NOTE_ID)},
            "body.note_id: Extra inputs are not permitted",
        ),
    ],
    ids=[
        "null-content",
        "negative-page",
        "bad-tag",
        "tags-not-list",
        "bad-link",
        "long-chapter",
        "extra",
    ],
)
async def test_add_note_rejects_invalid_body(client, write_db, patch, detail):
    body = {"material_id": str(factories.MATERIAL_ID), "content": "c", **patch}

    response = await client.post(f"{BASE}/add", json=body)

    assert response.status_code == 422
    assert response.json()["detail"].startswith(detail)
    write_db["insert_note"].assert_not_awaited()


async def test_add_note_rejects_unbalanced_quotes(client, write_db):
    response = await client.post(
        f"{BASE}/add",
        json={"material_id": str(factories.MATERIAL_ID), "content": 'odd " quote'},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "body.content: Assertion failed, Quotes are not balanced",
    }
    write_db["insert_note"].assert_not_awaited()


async def test_add_note_does_not_index_a_note_that_was_not_inserted(client, write_db):
    write_db["insert_note"].side_effect = database.NotFoundException("Material not found")

    response = await client.post(
        f"{BASE}/add", json={"material_id": str(factories.MATERIAL_ID), "content": "c"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "NotFoundError: Material not found"}
    write_db["index_insert"].assert_not_awaited()


async def test_add_note_reports_an_indexing_failure(client, write_db):
    write_db["index_insert"].side_effect = manticoresearch.ManticoreException("down")

    response = await client.post(
        f"{BASE}/add", json={"material_id": str(factories.MATERIAL_ID), "content": "c"}
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Manticoresearch error: down"}


def _update_body(**patch) -> dict:
    return {
        "material_id": str(factories.MATERIAL_ID),
        "link_id": None,
        "title": None,
        "content": "Новый текст",
        **patch,
    }


async def test_update_note_with_defaults(client, write_db):
    response = await client.patch(NOTE_URL, json=_update_body())

    assert response.status_code == 204
    assert response.content == b""
    write_db["update_note"].assert_awaited_once_with(
        note_id=factories.NOTE_ID,
        material_id=factories.MATERIAL_ID,
        link_id=None,
        title=None,
        content="Новый текст",
        chapter="0",
        page=0,
        tags=[],
    )
    write_db["index_update"].assert_awaited_once_with(
        note_id=factories.NOTE_ID, content="Новый текст", added_at=NOW
    )


async def test_update_note_with_every_field(client, write_db):
    response = await client.patch(
        NOTE_URL,
        json=_update_body(
            link_id=str(factories.OTHER_NOTE_ID),
            title="T",
            tags=["TAG"],
            chapter="",
            page=3,
        ),
    )

    assert response.status_code == 204
    write_db["update_note"].assert_awaited_once_with(
        note_id=factories.NOTE_ID,
        material_id=factories.MATERIAL_ID,
        link_id=factories.OTHER_NOTE_ID,
        title="T",
        content="Новый текст",
        chapter="",
        page=3,
        tags=["tag"],
    )


@pytest.mark.parametrize(
    "body",
    [
        {"material_id": str(factories.MATERIAL_ID), "content": "c"},
        _update_body(page=-1),
        _update_body(extra=1),
        _update_body(material_id=None),
    ],
    ids=["nullable-fields-omitted", "negative-page", "extra", "null-material"],
)
async def test_update_note_rejects_invalid_body(client, write_db, body):
    response = await client.patch(NOTE_URL, json=body)

    assert response.status_code == 422
    write_db["update_note"].assert_not_awaited()


async def test_update_note_that_is_missing_is_404_and_not_indexed(client, write_db):
    write_db["update_note"].side_effect = NOT_FOUND

    response = await client.patch(NOTE_URL, json=_update_body())

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY
    write_db["index_update"].assert_not_awaited()


async def test_update_note_rejects_bad_uuid(client, write_db):
    response = await client.patch(f"{BASE}/not-a-uuid", json=_update_body())

    assert response.status_code == 422
    write_db["update_note"].assert_not_awaited()


async def test_update_note_formats_content_like_a_new_note(client, write_db):
    response = await client.patch(
        NOTE_URL,
        json=_update_body(content='он сказал  "да" -- и x^2 ушёл', tags=["B", "a"]),
    )

    assert response.status_code == 204
    content = "Он сказал «да» — и x<sup>2</sup> ушёл"
    assert write_db["update_note"].await_args.kwargs["content"] == content
    assert write_db["update_note"].await_args.kwargs["tags"] == ["a", "b"]
    assert write_db["index_update"].await_args.kwargs["content"] == content


async def test_add_note_checks_the_material_and_the_linked_note(client, write_db):
    response = await client.post(
        f"{BASE}/add",
        json={
            "material_id": str(factories.MATERIAL_ID),
            "content": "c",
            "link_id": str(factories.OTHER_NOTE_ID),
        },
    )

    assert response.status_code == 201
    write_db["get_material"].assert_awaited_once_with(material_id=factories.MATERIAL_ID)
    write_db["get_link"].assert_awaited_once_with(note_id=factories.OTHER_NOTE_ID)


async def test_add_note_without_a_link_does_not_look_one_up(client, write_db):
    response = await client.post(
        f"{BASE}/add", json={"material_id": str(factories.MATERIAL_ID), "content": "c"}
    )

    assert response.status_code == 201
    write_db["get_link"].assert_not_awaited()


@pytest.mark.parametrize("missing", ["get_material", "get_link"])
@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        (
            "POST",
            f"{BASE}/add",
            {
                "material_id": str(factories.MATERIAL_ID),
                "content": "c",
                "link_id": str(factories.OTHER_NOTE_ID),
            },
        ),
        ("PATCH", NOTE_URL, _update_body(link_id=str(factories.OTHER_NOTE_ID))),
    ],
    ids=["add", "update"],
)
async def test_write_with_a_missing_reference_is_404_and_writes_nothing(
    client, write_db, missing, method, url, body
):
    write_db[missing].side_effect = NOT_FOUND

    response = await client.request(method, url, json=body)

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY
    for writer in ("insert_note", "update_note", "index_insert", "index_update"):
        write_db[writer].assert_not_awaited()


async def test_update_note_checks_the_new_link_for_a_cycle(client, write_db):
    response = await client.patch(
        NOTE_URL, json=_update_body(link_id=str(factories.OTHER_NOTE_ID))
    )

    assert response.status_code == 204
    write_db["is_link_cyclic"].assert_awaited_once_with(
        note_id=factories.NOTE_ID, link_id=factories.OTHER_NOTE_ID
    )


async def test_update_note_without_a_link_does_not_check_for_a_cycle(client, write_db):
    response = await client.patch(NOTE_URL, json=_update_body())

    assert response.status_code == 204
    write_db["get_link"].assert_not_awaited()
    write_db["is_link_cyclic"].assert_not_awaited()


async def test_update_note_creating_a_cycle_is_400(client, write_db):
    write_db["is_link_cyclic"].return_value = True

    response = await client.patch(
        NOTE_URL, json=_update_body(link_id=str(factories.OTHER_NOTE_ID))
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Link would create a cycle"}
    write_db["update_note"].assert_not_awaited()
    write_db["index_update"].assert_not_awaited()


@pytest.fixture
def autocompletion(mocker):
    return mocker.patch.object(
        manticoresearch, "autocompletion", mocker.AsyncMock(return_value=[])
    )


@pytest.mark.parametrize(
    ("params", "limit"),
    [({"query": "вой"}, 10), ({"query": "вой", "limit": 3}, 3)],
    ids=["default-limit", "explicit-limit"],
)
async def test_autocompletion_passes_query_and_limit(
    client, autocompletion, params, limit
):
    response = await client.get(f"{BASE}/autocompletion", params=params)

    assert response.status_code == 200
    assert response.json() == {"autocompletions": []}
    autocompletion.assert_awaited_once_with(query="вой", limit=limit)


async def test_autocompletion_strips_line_breaks(client, autocompletion):
    autocompletion.return_value = ["война<br/>и мир", "line\r\nbreak<br>", "plain"]

    response = await client.get(f"{BASE}/autocompletion", params={"query": "a"})

    assert response.json() == {"autocompletions": ["войнаи мир", "linebreak", "plain"]}


@pytest.mark.parametrize(
    "params", [{}, {"query": "a", "limit": "many"}], ids=["no-query", "bad-limit"]
)
async def test_autocompletion_rejects_invalid_query(client, autocompletion, params):
    response = await client.get(f"{BASE}/autocompletion", params=params)

    assert response.status_code == 422
    autocompletion.assert_not_awaited()


@pytest.mark.parametrize(
    ("params", "material_id"),
    [({}, None), ({"material_id": str(factories.MATERIAL_ID)}, factories.MATERIAL_ID)],
    ids=["all", "one-material"],
)
async def test_note_tags(client, mocker, params, material_id):
    get_tags = _patch(mocker, "get_sorted_tags", return_value=["тег", "a"])

    response = await client.get(f"{BASE}/tags", params=params)

    assert response.status_code == 200
    assert response.json() == {"tags": ["тег", "a"]}
    get_tags.assert_awaited_once_with(material_id=material_id)


@pytest.fixture
def get_note(mocker):
    return _patch(mocker, "get_note", return_value=factories.note())


async def test_possible_links_uses_the_tags_of_the_note(client, mocker, get_note):
    get_note.return_value = factories.note(tags={"a", "b"})
    candidate = factories.note(
        note_id=factories.OTHER_NOTE_ID, title="T", content="candidate", tags={"a"}
    )
    get_links = _patch(mocker, "get_possible_links", return_value=[candidate])

    response = await client.get(
        f"{BASE}/possible-links", params={"note_id": str(factories.NOTE_ID)}
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "note_id": str(factories.OTHER_NOTE_ID),
                "title": "T",
                "content": "candidate",
                "tags": ["a"],
            },
        ],
    }
    get_note.assert_awaited_once_with(note_id=factories.NOTE_ID)
    get_links.assert_awaited_once_with(note_id=factories.NOTE_ID, note_tags={"a", "b"})


async def test_possible_links_of_a_note_without_candidates(client, mocker, get_note):
    _patch(mocker, "get_possible_links", return_value=[])

    response = await client.get(
        f"{BASE}/possible-links", params={"note_id": str(factories.NOTE_ID)}
    )

    assert response.json() == {"items": []}


async def test_links_network_draws_the_linked_notes(client, mocker):
    get_note = _patch(mocker, "get_note", return_value=factories.note())
    root = factories.note()
    child = factories.note(note_id=factories.OTHER_NOTE_ID, link_id=root.note_id)
    unrelated = factories.note(note_id=OTHER_MATERIAL_NOTE_ID)
    get_notes = _patch(mocker, "get_notes", return_value=[root, child, unrelated])
    create_graphic = mocker.patch.object(
        notes_db, "create_graphic", mocker.Mock(return_value="<html>network</html>")
    )

    response = await client.get(
        f"{BASE}/links-network", params={"note_id": str(factories.NOTE_ID)}
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == "<html>network</html>"
    get_note.assert_awaited_once_with(note_id=factories.NOTE_ID)
    get_notes.assert_awaited_once_with()
    (graph,), kwargs = create_graphic.call_args
    assert kwargs == {}
    assert set(graph.nodes) == {str(factories.NOTE_ID), str(factories.OTHER_NOTE_ID)}
    assert set(graph.edges) == {(str(factories.OTHER_NOTE_ID), str(factories.NOTE_ID))}


async def test_links_network_of_a_missing_note_is_404(lenient_client, mocker):
    _patch(mocker, "get_note", side_effect=NOT_FOUND)
    get_notes = _patch(mocker, "get_notes", return_value=[factories.note()])

    response = await lenient_client.get(
        f"{BASE}/links-network", params={"note_id": str(factories.OTHER_NOTE_ID)}
    )

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY
    get_notes.assert_not_awaited()


def _info(note_id: UUID) -> str:
    return (
        f"ID: {note_id}\nNumber: 7\nMaterial ID: {factories.MATERIAL_ID}\n\nContent #tag"
    )


@pytest.fixture
def links_from_page(mocker):
    return _patch(mocker, "get_links_from_page", return_value=factories.page())


async def test_links_of_a_note_without_any(client, get_note, links_from_page):
    response = await client.get(
        f"{BASE}/links", params={"note_id": str(factories.NOTE_ID)}
    )

    assert response.status_code == 200
    assert response.json() == {
        "link_to": None,
        "links_from": [],
        "next_token": None,
        "total_count": 0,
    }
    get_note.assert_awaited_once_with(note_id=factories.NOTE_ID)
    links_from_page.assert_awaited_once_with(
        note_id=factories.NOTE_ID, params=pagination.PageParams()
    )


async def test_links_of_a_linked_note(client, mocker, get_note, links_from_page):
    target = factories.note(note_id=factories.OTHER_NOTE_ID)
    source = factories.note(note_id=OTHER_MATERIAL_NOTE_ID, link_id=factories.NOTE_ID)
    notes = {
        factories.NOTE_ID: factories.note(link_id=target.note_id),
        target.note_id: target,
    }
    get_note.side_effect = lambda *, note_id: notes[note_id]
    links_from_page.return_value = pagination.Page(
        items=[source], next_token="next", total_count=4
    )

    response = await client.get(
        f"{BASE}/links",
        params={"note_id": str(factories.NOTE_ID), "page_size": 1, "order": "desc"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "link_to": {
            "note_id": str(factories.OTHER_NOTE_ID),
            "info": _info(factories.OTHER_NOTE_ID),
        },
        "links_from": [
            {
                "note_id": str(OTHER_MATERIAL_NOTE_ID),
                "info": _info(OTHER_MATERIAL_NOTE_ID),
            },
        ],
        "next_token": "next",
        "total_count": 4,
    }
    assert get_note.await_args_list == [
        mocker.call(note_id=factories.NOTE_ID),
        mocker.call(note_id=factories.OTHER_NOTE_ID),
    ]
    links_from_page.assert_awaited_once_with(
        note_id=factories.NOTE_ID,
        params=pagination.PageParams(page_size=1, order=pagination.Order.DESC),
    )


@pytest.mark.xfail(
    strict=True,
    reason=TASK_GROUP_BUG.format(
        where="tracker/api/v1/notes.py:171",
        effect="a note linked to a deleted note gives 500 on /notes/links instead of 404",
    ),
)
async def test_links_of_a_note_linked_to_a_missing_note_is_404(
    lenient_client, get_note, links_from_page
):
    def find(*, note_id):
        if note_id == factories.NOTE_ID:
            return factories.note(link_id=factories.OTHER_NOTE_ID)
        raise NOT_FOUND

    get_note.side_effect = find

    response = await lenient_client.get(
        f"{BASE}/links", params={"note_id": str(factories.NOTE_ID)}
    )

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY


@pytest.mark.xfail(
    strict=True,
    reason=TASK_GROUP_BUG.format(
        where="tracker/api/v1/notes.py:171",
        effect="a malformed next_token on /notes/links is 500 instead of 422",
    ),
)
async def test_links_maps_invalid_token_to_422(lenient_client, get_note, links_from_page):
    links_from_page.side_effect = database.InvalidNextTokenException(
        "next_token is malformed"
    )

    response = await lenient_client.get(
        f"{BASE}/links",
        params={"note_id": str(factories.NOTE_ID), "next_token": "garbage"},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        f"{BASE}/{factories.NOTE_ID}",
        f"{BASE}/links?note_id={factories.NOTE_ID}",
        f"{BASE}/possible-links?note_id={factories.NOTE_ID}",
    ],
    ids=["get", "links", "possible-links"],
)
async def test_reads_of_a_missing_note_are_404(
    client, mocker, get_note, links_from_page, path
):
    get_note.side_effect = NOT_FOUND
    get_links = _patch(mocker, "get_possible_links", return_value=[])

    response = await client.get(path)

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY
    links_from_page.assert_not_awaited()
    get_links.assert_not_awaited()


@pytest.mark.parametrize("path", ["links", "possible-links", "links-network"])
@pytest.mark.parametrize("params", [{}, {"note_id": "x"}], ids=["missing", "bad-uuid"])
async def test_link_reads_require_a_valid_note_id(client, get_note, path, params):
    response = await client.get(f"{BASE}/{path}", params=params)

    assert response.status_code == 422
    assert response.json()["detail"].startswith("query.note_id: ")
    get_note.assert_not_awaited()


async def test_get_note(client, get_note):
    get_note.return_value = factories.note(
        title="Заголовок", link_id=factories.OTHER_NOTE_ID, links_count=0
    )

    response = await client.get(NOTE_URL)

    assert response.status_code == 200
    assert response.json() == {
        "note": factories.note_json(
            title="Заголовок", link_id=str(factories.OTHER_NOTE_ID), links_count=0
        ),
    }
    get_note.assert_awaited_once_with(note_id=factories.NOTE_ID)


async def test_get_note_rejects_bad_uuid(client, get_note):
    response = await client.get(f"{BASE}/not-a-uuid")

    assert response.status_code == 422
    get_note.assert_not_awaited()


@pytest.mark.parametrize(
    ("method", "suffix", "db_function"),
    [("DELETE", "", "delete_note"), ("POST", "/restore", "restore_note")],
    ids=["delete", "restore"],
)
class TestDeleteAndRestore:
    @pytest.fixture(autouse=True)
    def _not_linked(self, mocker):
        return _patch(mocker, "count_links_to", return_value=0)

    async def test_runs_the_action(self, client, mocker, method, suffix, db_function):
        run = _patch(mocker, db_function, return_value=None)

        response = await client.request(method, f"{NOTE_URL}{suffix}")

        assert response.status_code == 204
        assert response.content == b""
        run.assert_awaited_once_with(note_id=factories.NOTE_ID)

    async def test_missing_note_is_404(self, client, mocker, method, suffix, db_function):
        _patch(mocker, db_function, side_effect=NOT_FOUND)

        response = await client.request(method, f"{NOTE_URL}{suffix}")

        assert response.status_code == 404
        assert response.json() == NOT_FOUND_BODY

    async def test_rejects_bad_uuid(self, client, mocker, method, suffix, db_function):
        run = _patch(mocker, db_function, return_value=None)

        response = await client.request(method, f"{BASE}/1{suffix}")

        assert response.status_code == 422
        run.assert_not_awaited()


async def test_delete_of_a_linked_note_is_409(client, mocker):
    count_links_to = _patch(mocker, "count_links_to", return_value=2)
    delete = _patch(mocker, "delete_note", return_value=None)

    response = await client.delete(NOTE_URL)

    assert response.status_code == 409
    assert response.json() == {"detail": "Note is linked from 2 notes"}
    count_links_to.assert_awaited_once_with(note_id=factories.NOTE_ID)
    delete.assert_not_awaited()


async def test_deleted_note_is_404_until_restored(client, mocker):
    state = {"is_deleted": False}

    async def get(*, note_id):
        if state["is_deleted"]:
            raise NOT_FOUND
        return factories.note(note_id=note_id)

    async def set_deleted(*, note_id, is_deleted):
        state["is_deleted"] = is_deleted

    mocker.patch.object(notes_db, "get_note", get)
    mocker.patch.object(notes_db, "_del_or_restore", set_deleted)
    _patch(mocker, "count_links_to", return_value=0)

    assert (await client.get(NOTE_URL)).status_code == 200
    assert (await client.delete(NOTE_URL)).status_code == 204
    deleted = await client.get(NOTE_URL)
    assert deleted.status_code == 404
    assert deleted.json() == NOT_FOUND_BODY
    assert (await client.post(f"{NOTE_URL}/restore")).status_code == 204
    assert (await client.get(NOTE_URL)).status_code == 200


@pytest.fixture
def repeat_note(mocker):
    return mocker.patch.object(kafka, "repeat_note", mocker.AsyncMock())


async def test_repeat_queue_sends_an_existing_note(client, get_note, repeat_note):
    response = await client.post(f"{NOTE_URL}/repeat-queue")

    assert response.status_code == 204
    get_note.assert_awaited_once_with(note_id=factories.NOTE_ID)
    repeat_note.assert_awaited_once_with(factories.NOTE_ID)


async def test_repeat_queue_does_not_send_a_missing_note(client, get_note, repeat_note):
    get_note.side_effect = NOT_FOUND

    response = await client.post(f"{NOTE_URL}/repeat-queue")

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY
    repeat_note.assert_not_awaited()


async def test_repeat_queue_reports_a_broker_failure_as_503(
    client, get_note, repeat_note
):
    repeat_note.side_effect = kafka.KafkaSendError("broker down")

    response = await client.post(f"{NOTE_URL}/repeat-queue")

    assert response.status_code == 503
    assert response.json() == {"detail": "Kafka unavailable"}
