from types import SimpleNamespace
from uuid import UUID

import pytest

from tests.unit.api import factories
from tracker.cards import db as cards_db
from tracker.common import database, pagination
from tracker.materials import db as materials_db
from tracker.notes import db as notes_db


URL = "/api/v1/cards/"


@pytest.fixture
def get_cards_page(mocker):
    return mocker.patch.object(
        cards_db, "get_cards_page", mocker.AsyncMock(return_value=factories.page())
    )


async def test_list_cards_returns_an_empty_page(client, get_cards_page):
    response = await client.get(URL)

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_token": None, "total_count": 0}
    get_cards_page.assert_awaited_once_with(
        material_id=None, params=pagination.PageParams()
    )


async def test_list_cards_serializes_the_page(client, get_cards_page):
    answered = factories.card(answer="Толстой", note_title="Заголовок", note_page=12)
    get_cards_page.return_value = pagination.Page(
        items=[factories.card(), answered], next_token="next", total_count=5
    )

    response = await client.get(URL)

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            factories.card_json(),
            factories.card_json(answer="Толстой", note_title="Заголовок", note_page=12),
        ],
        "next_token": "next",
        "total_count": 5,
    }


async def test_list_cards_passes_filter_and_page_params(client, get_cards_page):
    response = await client.get(
        URL,
        params={
            "material_id": str(factories.MATERIAL_ID),
            "page_size": 7,
            "order": "asc",
            "next_token": "token",
        },
    )

    assert response.status_code == 200
    get_cards_page.assert_awaited_once_with(
        material_id=factories.MATERIAL_ID,
        params=pagination.PageParams(
            page_size=7, order=pagination.Order.ASC, next_token="token"
        ),
    )


@pytest.mark.parametrize("page_size", [1, pagination.MAX_PAGE_SIZE])
async def test_list_cards_accepts_page_size_at_the_bounds(
    client, get_cards_page, page_size
):
    response = await client.get(URL, params={"page_size": page_size})

    assert response.status_code == 200
    assert get_cards_page.await_args.kwargs["params"].page_size == page_size


async def test_list_cards_accepts_next_token_of_max_length(client, get_cards_page):
    token = "a" * pagination.MAX_TOKEN_LENGTH

    response = await client.get(URL, params={"next_token": token})

    assert response.status_code == 200
    assert get_cards_page.await_args.kwargs["params"].next_token == token


@pytest.mark.parametrize(
    ("params", "location"),
    [
        ({"page_size": 0}, "query.page_size"),
        ({"page_size": -1}, "query.page_size"),
        ({"page_size": pagination.MAX_PAGE_SIZE + 1}, "query.page_size"),
        ({"page_size": "many"}, "query.page_size"),
        ({"next_token": "a" * (pagination.MAX_TOKEN_LENGTH + 1)}, "query.next_token"),
        ({"order": "random"}, "query.order"),
        ({"material_id": "not-a-uuid"}, "query.material_id"),
        ({"material_id": ""}, "query.material_id"),
    ],
    ids=[
        "page-size-zero",
        "page-size-negative",
        "page-size-over-max",
        "page-size-not-int",
        "token-too-long",
        "unknown-order",
        "bad-uuid",
        "empty-uuid",
    ],
)
async def test_list_cards_rejects_invalid_query(client, get_cards_page, params, location):
    response = await client.get(URL, params=params)

    assert response.status_code == 422
    assert response.json()["detail"].startswith(f"{location}: ")
    get_cards_page.assert_not_awaited()


async def test_list_cards_maps_invalid_token_to_422(client, get_cards_page):
    get_cards_page.side_effect = database.InvalidNextTokenException("Invalid nextToken")

    response = await client.get(URL, params={"next_token": "garbage"})

    assert response.status_code == 422
    assert response.json() == {"detail": "InvalidNextToken: Invalid nextToken"}


@pytest.fixture
def card_refs(mocker):
    """The material and the note of the card exist and belong together."""
    return SimpleNamespace(
        get_material=mocker.patch.object(
            materials_db,
            "get_material_api",
            mocker.AsyncMock(return_value=factories.material()),
        ),
        get_note=mocker.patch.object(
            notes_db, "get_note", mocker.AsyncMock(return_value=factories.note())
        ),
    )


@pytest.fixture
def add_card(mocker, card_refs):
    return mocker.patch.object(
        cards_db, "add_card", mocker.AsyncMock(return_value=factories.CARD_ID)
    )


CARD_BODY = {
    "material_id": str(factories.MATERIAL_ID),
    "note_id": str(factories.NOTE_ID),
    "question": "q",
}


async def test_create_card_checks_the_material_and_the_note(client, add_card, card_refs):
    response = await client.post(URL, json=CARD_BODY)

    assert response.status_code == 201
    card_refs.get_material.assert_awaited_once_with(material_id=factories.MATERIAL_ID)
    card_refs.get_note.assert_awaited_once_with(note_id=factories.NOTE_ID)


@pytest.mark.parametrize("missing", ["get_material", "get_note"])
async def test_create_card_with_a_missing_reference_is_404(
    client, add_card, card_refs, missing
):
    getattr(card_refs, missing).side_effect = database.NotFoundException("not found")

    response = await client.post(URL, json=CARD_BODY)

    assert response.status_code == 404
    assert response.json() == {"detail": "NotFoundError: not found"}
    add_card.assert_not_awaited()


async def test_create_card_for_a_note_of_another_material_is_400(
    client, add_card, card_refs
):
    card_refs.get_note.return_value = factories.note(
        material_id=factories.OTHER_MATERIAL_ID
    )

    response = await client.post(URL, json=CARD_BODY)

    assert response.status_code == 400
    assert response.json() == {"detail": "Note belongs to another material"}
    add_card.assert_not_awaited()


async def test_create_card(client, add_card):
    response = await client.post(
        URL,
        json={
            "material_id": str(factories.MATERIAL_ID),
            "note_id": str(factories.NOTE_ID),
            "question": "  Кто автор?  ",
            "answer": "Толстой",
        },
    )

    assert response.status_code == 201
    assert response.json() == {"card_id": str(factories.CARD_ID)}
    add_card.assert_awaited_once_with(
        material_id=factories.MATERIAL_ID,
        note_id=factories.NOTE_ID,
        question="Кто автор?",
        answer="Толстой",
    )


async def test_create_card_without_answer_passes_none(client, add_card):
    response = await client.post(
        URL,
        json={
            "material_id": str(factories.MATERIAL_ID),
            "note_id": str(factories.NOTE_ID),
            "question": "q",
        },
    )

    assert response.status_code == 201
    assert add_card.await_args.kwargs["answer"] is None


@pytest.mark.parametrize(
    ("patch", "detail"),
    [
        ({"extra": 1}, "body.extra: Extra inputs are not permitted"),
        ({"note_id": "x"}, "body.note_id: Input should be a valid UUID"),
        ({"question": None}, "body.question: Input should be a valid string"),
        ({"question": 5}, "body.question: Input should be a valid string"),
    ],
    ids=["extra-field", "bad-uuid", "null-question", "int-question"],
)
async def test_create_card_rejects_invalid_body(client, add_card, patch, detail):
    body = {
        "material_id": str(factories.MATERIAL_ID),
        "note_id": str(factories.NOTE_ID),
        "question": "q",
        **patch,
    }

    response = await client.post(URL, json=body)

    assert response.status_code == 422
    assert response.json()["detail"].startswith(detail)
    add_card.assert_not_awaited()


@pytest.mark.parametrize(
    ("exc", "status_code", "detail"),
    [
        (
            database.NotFoundException("Note not found"),
            404,
            "NotFoundError: Note not found",
        ),
        (
            database.AlreadyExistsException("Card exists"),
            409,
            "AlreadyExistsError: Card exists",
        ),
    ],
    ids=["missing-note", "duplicate"],
)
async def test_create_card_maps_database_errors(
    client, add_card, exc, status_code, detail
):
    add_card.side_effect = exc

    response = await client.post(
        URL,
        json={
            "material_id": str(factories.MATERIAL_ID),
            "note_id": str(factories.NOTE_ID),
            "question": "q",
        },
    )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}


@pytest.mark.parametrize(
    ("params", "material_id"),
    [({}, None), ({"material_id": str(factories.MATERIAL_ID)}, factories.MATERIAL_ID)],
    ids=["all", "one-material"],
)
async def test_notes_with_cards_are_sorted(client, mocker, params, material_id):
    ids = {
        UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"),
        UUID("00000000-0000-4000-8000-000000000001"),
        UUID("88888888-8888-4888-8888-888888888888"),
    }
    get_notes = mocker.patch.object(
        cards_db, "get_notes_with_cards", mocker.AsyncMock(return_value=ids)
    )

    response = await client.get("/api/v1/cards/notes-with-cards", params=params)

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            "00000000-0000-4000-8000-000000000001",
            "88888888-8888-4888-8888-888888888888",
            "ffffffff-ffff-4fff-8fff-ffffffffffff",
        ],
    }
    get_notes.assert_awaited_once_with(material_id=material_id)


async def test_notes_with_cards_of_nothing_is_an_empty_list(client, mocker):
    mocker.patch.object(
        cards_db, "get_notes_with_cards", mocker.AsyncMock(return_value=set())
    )

    response = await client.get("/api/v1/cards/notes-with-cards")

    assert response.json() == {"items": []}


async def test_notes_with_cards_rejects_bad_uuid(client):
    response = await client.get(
        "/api/v1/cards/notes-with-cards", params={"material_id": "1"}
    )

    assert response.status_code == 422
