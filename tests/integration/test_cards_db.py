from uuid import UUID

import pytest

from tests.integration import factories, helpers, helpers_materials as h
from tracker.cards import db
from tracker.common import sort_keys
from tracker.common.pagination import PageParams
from tracker.models import enums, models


FIXED_ID = "018e4a6c-0000-7000-8000-00000000abcd"


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> h.Clock:
    return h.freeze_clock(monkeypatch)


async def add_card(clock: h.Clock, **card) -> UUID:
    """Add a card at its own second, so cards have distinct `added_at` and `sort_key`."""
    clock.tick()
    return await db.add_card(**card)


@pytest.fixture
async def cards(clock: h.Clock) -> dict[str, UUID]:
    """Two materials: the first has two notes with cards, the second one note with a card."""
    first = await h.queued(
        clock,
        title="First",
        authors="First author",
        material_type=enums.MaterialTypesEnum.article,
    )
    second = await h.queued(clock, title="Second", authors="Second author")
    first_note = await factories.insert_note(
        material_id=first,
        title="First note",
        content="First content.",
        chapter="3",
        page=14,
    )
    other_note = await factories.insert_note(material_id=first, page=2)
    second_note = await factories.insert_note(material_id=second)
    await factories.insert_note(material_id=second, page=2)

    return {
        "first": first,
        "second": second,
        "first_note": first_note,
        "other_note": other_note,
        "second_note": second_note,
        "oldest": await add_card(
            clock,
            material_id=first,
            note_id=first_note,
            question="Вопрос?",
            answer="Ответ.",
        ),
        "middle": await add_card(
            clock, material_id=first, note_id=other_note, question="Q2"
        ),
        "foreign": await add_card(
            clock,
            material_id=second,
            note_id=second_note,
            question="Q3",
            answer="A3",
        ),
        "newest": await add_card(
            clock,
            material_id=first,
            note_id=first_note,
            question="Q4",
            answer="A4",
        ),
    }


# add_card


async def test_add_card_stores_every_column(clock, mocker):
    material_id = await h.queued(clock)
    note_id = await factories.insert_note(material_id=material_id)
    mocker.patch.object(models, "generate_id", return_value=FIXED_ID)

    card_id = await db.add_card(
        material_id=material_id,
        note_id=note_id,
        question="Что такое keyset?",
        answer="Постраничный обход по ключу.",
    )

    assert card_id == UUID(FIXED_ID)
    assert await factories.fetch_row(models.Cards, card_id) == {
        "card_id": UUID(FIXED_ID),
        "material_id": material_id,
        "note_id": note_id,
        "question": "Что такое keyset?",
        "answer": "Постраничный обход по ключу.",
        "added_at": clock.now,
        "sort_key": f"2024-03-15T12:30:46.123456$${FIXED_ID}",
    }


async def test_add_card_sort_key_matches_the_generator(clock):
    material_id = await h.queued(clock)
    note_id = await factories.insert_note(material_id=material_id)

    card_id = await db.add_card(material_id=material_id, note_id=note_id, question="Q")

    row = await factories.fetch_row(models.Cards, card_id)
    assert row["sort_key"] == sort_keys.card_sort_key(
        added_at=row["added_at"],
        card_id=card_id,
    )


@pytest.mark.parametrize("answer", [None, ""], ids=["None", "empty"])
async def test_add_card_stores_a_card_without_an_answer(clock, answer):
    material_id = await h.queued(clock)
    note_id = await factories.insert_note(material_id=material_id)

    card_id = await db.add_card(
        material_id=material_id,
        note_id=note_id,
        question="Q",
        answer=answer,
    )

    assert (await factories.fetch_row(models.Cards, card_id))["answer"] == answer


async def test_add_card_answer_is_none_by_default(clock):
    material_id = await h.queued(clock)
    note_id = await factories.insert_note(material_id=material_id)

    card_id = await db.add_card(material_id=material_id, note_id=note_id, question="Q")

    assert (await factories.fetch_row(models.Cards, card_id))["answer"] is None


async def test_add_card_stores_a_long_unicode_question(clock):
    material_id = await h.queued(clock)
    note_id = await factories.insert_note(material_id=material_id)
    question = "Ж" * 100_000

    card_id = await db.add_card(
        material_id=material_id, note_id=note_id, question=question
    )

    assert (await factories.fetch_row(models.Cards, card_id))["question"] == question


async def test_add_card_allows_several_cards_for_one_note(clock):
    material_id = await h.queued(clock)
    note_id = await factories.insert_note(material_id=material_id)

    first = await db.add_card(material_id=material_id, note_id=note_id, question="Same")
    second = await db.add_card(material_id=material_id, note_id=note_id, question="Same")

    assert first != second
    assert await db.get_cards_count(note_id=note_id) == 2


async def test_add_card_accepts_unknown_note_and_material_current_behaviour():
    card_id = await db.add_card(
        material_id=h.MISSING_ID, note_id=h.MISSING_ID, question="Q"
    )

    row = await factories.fetch_row(models.Cards, card_id)
    assert (row["material_id"], row["note_id"]) == (h.MISSING_ID, h.MISSING_ID)


# get_cards, get_cards_page


async def test_get_cards_returns_a_card_with_its_note_and_material(clock, cards):
    result = await db.get_cards(note_id=cards["first_note"], material_id=cards["first"])
    card = result[-1]

    assert card == db.Card(
        card_id=cards["oldest"],
        note_id=cards["first_note"],
        material_id=cards["first"],
        question="Вопрос?",
        answer="Ответ.",
        # the two materials took the first two seconds of the clock
        added_at=helpers.NOW.replace(second=helpers.NOW.second + 3),
        note_title="First note",
        note_content="First content.",
        note_chapter="3",
        note_page=14,
        material_title="First",
        material_authors="First author",
        material_type=enums.MaterialTypesEnum.article,
    )


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({}, ["newest", "foreign", "middle", "oldest"]),
        ({"note_id": "first_note"}, ["newest", "oldest"]),
        ({"note_id": "other_note"}, ["middle"]),
        ({"material_id": "first"}, ["newest", "middle", "oldest"]),
        ({"material_id": "second"}, ["foreign"]),
        ({"note_id": "first_note", "material_id": "first"}, ["newest", "oldest"]),
        ({"note_id": "first_note", "material_id": "second"}, []),
        ({"note_id": "missing"}, []),
        ({"material_id": "missing"}, []),
    ],
    ids=[
        "no filters",
        "note with two cards",
        "note with one card",
        "first material",
        "second material",
        "note and its material",
        "note and another material",
        "unknown note",
        "unknown material",
    ],
)
async def test_cards_filters(cards, filters, expected):
    ids = cards | {"missing": h.MISSING_ID}
    filters = {name: ids[value] for name, value in filters.items()}

    result = await db.get_cards(**filters)

    assert [card.card_id for card in result] == [cards[name] for name in expected]
    assert await db.get_cards_count(**filters) == len(expected)


async def test_get_cards_accepts_a_string_material_id(cards):
    result = await db.get_cards(material_id=str(cards["second"]))

    assert [card.card_id for card in result] == [cards["foreign"]]


async def test_cards_are_empty_on_an_empty_database():
    page = await db.get_cards_page(material_id=None, params=PageParams())

    assert await db.get_cards() == []
    assert (page.items, page.total_count, page.next_token) == ([], 0, None)
    assert await db.get_notes_with_cards() == set()
    assert await db.get_all_cards_count() == {}
    assert await db.get_cards_count() == 0


@pytest.mark.parametrize(
    ("material", "expected"),
    [
        (None, ["newest", "foreign", "middle", "oldest"]),
        ("first", ["newest", "middle", "oldest"]),
        ("second", ["foreign"]),
        ("missing", []),
    ],
)
async def test_cards_page_returns_the_same_cards_as_the_full_listing(
    cards, material, expected
):
    material_id = (cards | {"missing": h.MISSING_ID, None: None})[material]

    page = await db.get_cards_page(material_id=material_id, params=PageParams())

    assert page.items == await db.get_cards(material_id=material_id)
    assert [card.card_id for card in page.items] == [cards[name] for name in expected]
    assert page.total_count == len(expected)
    assert page.next_token is None


async def test_card_of_a_missing_note_is_counted_but_not_listed_current_behaviour(clock):
    material_id = await h.queued(clock)
    await db.add_card(material_id=material_id, note_id=h.MISSING_ID, question="Orphan")

    assert await db.get_cards(material_id=material_id) == []
    assert await db.get_cards_count(material_id=material_id) == 1
    assert await db.get_all_cards_count() == {material_id: 1}


async def test_card_shows_the_material_of_its_note_current_behaviour(clock):
    note_material = await h.queued(clock, title="Material of the note")
    card_material = await h.queued(clock, title="Material of the card")
    note_id = await factories.insert_note(material_id=note_material)
    card_id = await db.add_card(material_id=card_material, note_id=note_id, question="Q")

    [card] = await db.get_cards(material_id=card_material)

    assert (card.card_id, card.material_id) == (card_id, card_material)
    assert card.material_title == "Material of the note"


# get_notes_with_cards, get_all_cards_count, get_cards_count


async def test_notes_with_cards_are_distinct_notes_having_a_card(cards):
    assert await db.get_notes_with_cards() == {
        cards["first_note"],
        cards["other_note"],
        cards["second_note"],
    }


async def test_notes_with_cards_of_a_material(cards):
    assert await db.get_notes_with_cards(material_id=cards["second"]) == {
        cards["second_note"]
    }
    assert await db.get_notes_with_cards(material_id=h.MISSING_ID) == set()


async def test_all_cards_count_is_grouped_by_material(cards):
    assert await db.get_all_cards_count() == {cards["first"]: 3, cards["second"]: 1}
