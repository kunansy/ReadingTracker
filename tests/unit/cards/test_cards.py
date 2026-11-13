from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from tests.unit.helpers import NOW, compile_sql, uid
from tracker.cards import db, schemas
from tracker.common import database, pagination
from tracker.models import enums


NOTE_ID, MATERIAL_ID = uid(1), uid(2)
CARDS_QUERY = (
    "SELECT cards.card_id, cards.material_id, cards.note_id, cards.question, cards.answer, "
    "cards.added_at, cards.sort_key, notes.title AS note_title, "
    "notes.content AS note_content, notes.chapter AS note_chapter, notes.page AS note_page, "
    "materials.authors AS material_authors, materials.material_type, "
    "materials.title AS material_title "
    "FROM cards JOIN notes ON cards.note_id = notes.note_id "
    "JOIN materials ON notes.material_id = materials.material_id"
)
ORDER = "ORDER BY cards.added_at DESC"


def _card_fields(**overrides):
    return {
        "card_id": uid(3),
        "note_id": NOTE_ID,
        "material_id": MATERIAL_ID,
        "question": "Что такое MVCC?",
        "answer": None,
        "added_at": NOW,
        "note_title": None,
        "note_content": "content",
        "note_chapter": "1",
        "note_page": 0,
        "material_title": "PostgreSQL изнутри",
        "material_authors": "Рогов",
        "material_type": "book",
    } | overrides


def test_cards_statement_without_filters():
    assert compile_sql(db._get_cards_stmt()) == f"{CARDS_QUERY} {ORDER}"


@pytest.mark.parametrize(
    ("filters", "expected_where"),
    [
        ({"note_id": NOTE_ID}, f"cards.note_id = '{NOTE_ID}'"),
        ({"material_id": MATERIAL_ID}, f"cards.material_id = '{MATERIAL_ID}'"),
        ({"material_id": str(MATERIAL_ID)}, f"cards.material_id = '{MATERIAL_ID}'"),
        (
            {"note_id": NOTE_ID, "material_id": MATERIAL_ID},
            f"cards.note_id = '{NOTE_ID}' AND cards.material_id = '{MATERIAL_ID}'",
        ),
    ],
    ids=["note", "material", "material-as-string", "note-and-material"],
)
def test_cards_statement_filters(filters, expected_where):
    assert compile_sql(db._get_cards_stmt(**filters)) == (
        f"{CARDS_QUERY} WHERE {expected_where} {ORDER}"
    )


@pytest.mark.parametrize(
    "filters",
    [{"note_id": None}, {"material_id": None}, {"material_id": ""}],
    ids=["no-note", "no-material", "empty-material"],
)
def test_cards_statement_empty_filter_is_not_applied(filters):
    assert compile_sql(db._get_cards_stmt(**filters)) == f"{CARDS_QUERY} {ORDER}"


@pytest.mark.parametrize("material_id", [MATERIAL_ID, None], ids=["material", "all"])
async def test_cards_page_is_bound_to_the_material_filter(mocker, material_id):
    expected = pagination.Page(items=[], next_token=None, total_count=0)
    fetch_page = mocker.patch.object(
        pagination,
        "fetch_page",
        mocker.AsyncMock(return_value=expected),
    )

    page = await db.get_cards_page(
        material_id=material_id,
        params=pagination.PageParams(page_size=100),
    )

    assert page is expected
    kwargs = fetch_page.await_args.kwargs
    assert compile_sql(fetch_page.await_args.args[0]) == compile_sql(
        db._get_cards_stmt(material_id=material_id),
    )
    assert kwargs["request"].order == pagination.Order.DESC
    assert kwargs["request"].params == {
        "order": "desc",
        "max_items": "100",
        "material_id": str(material_id) if material_id else "",
    }
    assert compile_sql(kwargs["key"]) == 'cards.sort_key COLLATE "C"'
    row = SimpleNamespace(**_card_fields(), sort_key="k", cursor="c")
    assert kwargs["to_item"](row) == db.Card(**_card_fields())


async def test_cards_page_rejects_token_of_another_material(mocker):
    fetch_page = mocker.patch.object(pagination, "fetch_page", mocker.AsyncMock())
    token = pagination.encode_next_token(
        {"order": "desc", "max_items": "20", "material_id": ""},
        {"cursor": "c"},
    )

    with pytest.raises(database.InvalidNextTokenException):
        await db.get_cards_page(
            material_id=MATERIAL_ID,
            params=pagination.PageParams(next_token=token),
        )

    fetch_page.assert_not_awaited()


def test_card_model_parses_material_type_and_optional_fields():
    card = db.Card(**_card_fields())

    assert card.material_type is enums.MaterialTypesEnum.book
    assert card.answer is None
    assert card.note_title is None


@pytest.mark.parametrize(
    ("field", "value"),
    [("question", None), ("note_content", None), ("note_page", "x"), ("material_type", "x")],
    ids=lambda value: f"{value!r}",
)
def test_card_model_rejects_invalid_field(field, value):
    with pytest.raises(ValidationError) as exc_info:
        db.Card(**_card_fields(**{field: value}))

    assert exc_info.value.errors()[0]["loc"] == (field,)


def _create_request(**overrides):
    return {
        "material_id": str(MATERIAL_ID),
        "note_id": str(NOTE_ID),
        "question": "Что такое MVCC?",
    } | overrides


def test_create_card_request_defaults_and_strips():
    request = schemas.CreateCardRequest(**_create_request(question="  Вопрос?  ", answer=" да "))

    assert (request.question, request.answer) == ("Вопрос?", "да")
    assert schemas.CreateCardRequest(**_create_request()).answer is None
    assert schemas.CreateCardRequest(**_create_request(answer=None)).answer is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("material_id", "x"),
        ("material_id", None),
        ("note_id", ""),
        ("note_id", None),
        ("question", None),
        ("question", 5),
        ("answer", 5),
        ("card_id", str(uid(9))),
    ],
    ids=lambda value: f"{value!r}",
)
def test_create_card_request_rejects_invalid_field(field, value):
    with pytest.raises(ValidationError) as exc_info:
        schemas.CreateCardRequest(**_create_request(**{field: value}))

    assert exc_info.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize("field", ["material_id", "note_id", "question"])
def test_create_card_request_requires_field(field):
    payload = _create_request()
    del payload[field]

    with pytest.raises(ValidationError) as exc_info:
        schemas.CreateCardRequest(**payload)

    assert [(e["loc"], e["type"]) for e in exc_info.value.errors()] == [((field,), "missing")]


@pytest.mark.parametrize("question", ["", "   "], ids=["empty", "blank"])
def test_create_card_request_accepts_blank_question_current_behaviour(question):
    assert schemas.CreateCardRequest(**_create_request(question=question)).question == ""


def test_create_card_request_has_no_length_limit_current_behaviour():
    question = "я" * 100_000

    assert schemas.CreateCardRequest(**_create_request(question=question)).question == question


def test_list_cards_response_validates_items_and_pagination_fields():
    response = schemas.ListCardsResponse(
        next_token="t",
        total_count=1,
        items=[_card_fields()],
    )

    assert response.items[0].card_id == uid(3)
    assert response.items[0].material_type is enums.MaterialTypesEnum.book
    with pytest.raises(ValidationError):
        schemas.ListCardsResponse(items=[])
    with pytest.raises(ValidationError):
        schemas.ListCardsResponse(
            next_token=None,
            total_count=1,
            items=[_card_fields(material_type="podcast")],
        )


def test_list_item_matches_the_db_card_model():
    card = db.Card(**_card_fields())

    assert schemas._ListCardsItem(**card.model_dump()).model_dump() == card.model_dump()


def test_simple_card_responses():
    assert schemas.CreateCardResponse(card_id=str(uid(3))).card_id == uid(3)
    assert schemas.ListNotesWithCardsResponse(items=[str(NOTE_ID)]).items == [NOTE_ID]
    assert schemas.ListNotesWithCardsResponse(items=[]).items == []

    with pytest.raises(ValidationError):
        schemas.CreateCardResponse(card_id="x")
    with pytest.raises(ValidationError):
        schemas.ListNotesWithCardsResponse(items=["x"])
