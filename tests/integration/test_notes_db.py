import datetime
import uuid
from collections import defaultdict

import pytest
import sqlalchemy.sql as sa

from tests.integration import (
    factories,
    helpers_notes as helpers,
)
from tracker.common import database, sort_keys
from tracker.common.pagination import PageParams
from tracker.models import enums, models
from tracker.notes import db as notes_db


MISSING_ID = uuid.UUID("00000000-0000-4000-8000-000000000000")


@pytest.fixture
async def material_id() -> uuid.UUID:
    return await factories.insert_material(title="Notes material")


async def _note_row(note_id: uuid.UUID) -> dict:
    row = await factories.fetch_row(models.Notes, note_id)
    assert row is not None
    return row


async def test_insert_note_stores_every_column(material_id):
    link_id = await factories.insert_note(material_id=material_id)

    note_id = await notes_db.insert_note(
        material_id=material_id,
        link_id=link_id,
        title="Title",
        content="Content of the note.",
        chapter="Chapter 3",
        page=42,
        tags=["first", "second"],
    )

    row = await _note_row(note_id)
    added_at = row.pop("added_at")
    assert isinstance(added_at, datetime.datetime)
    assert added_at.tzinfo is None
    assert row == {
        "note_id": note_id,
        "note_number": 2,
        "material_id": material_id,
        "link_id": link_id,
        "title": "Title",
        "content": "Content of the note.",
        "chapter": "Chapter 3",
        "page": 42,
        "tags": ["first", "second"],
        "is_deleted": False,
        "sort_key": f"{material_id}$$0000000003$$0000000042$${note_id}",
    }


async def test_insert_note_returns_the_generated_id(material_id, mocker):
    generated = "018f0000-0000-7000-8000-000000000001"
    mocker.patch("tracker.models.models.generate_id", return_value=generated)

    note_id = await factories.insert_note(material_id=material_id)

    assert note_id == uuid.UUID(generated)
    assert await factories.count_rows(models.Notes) == 1
    assert (await _note_row(note_id))["note_id"] == uuid.UUID(generated)


@pytest.mark.parametrize(
    ("chapter", "page"),
    [
        ("", 0),
        ("7", 1),
        ("007", 12),
        ("Глава 12", 2_147_483_647),
        ("no digits", 5),
        ("1.2", 3),
        ("12345678901", 9),
    ],
    ids=[
        "empty",
        "plain",
        "leading-zeros",
        "cyrillic-max-page",
        "no-digits",
        "dotted",
        "over-width",
    ],
)
async def test_insert_note_sort_key_matches_the_generator(material_id, chapter, page):
    note_id = await factories.insert_note(
        material_id=material_id,
        chapter=chapter,
        page=page,
    )

    row = await _note_row(note_id)

    assert row["sort_key"] == sort_keys.note_sort_key(
        material_id=material_id,
        chapter=chapter,
        page=page,
        note_id=note_id,
    )


async def test_insert_note_numbers_follow_the_sequence(material_id):
    other_material_id = await factories.insert_material()

    ids = [
        await factories.insert_note(material_id=material_id),
        await factories.insert_note(material_id=other_material_id),
        await factories.insert_note(material_id=material_id),
    ]

    numbers = [(await _note_row(note_id))["note_number"] for note_id in ids]
    assert numbers == [1, 2, 3]


async def test_insert_note_number_is_not_reused_after_a_failed_insert(material_id):
    await factories.insert_note(material_id=material_id, title="Same")
    with pytest.raises(database.AlreadyExistsException):
        await factories.insert_note(material_id=material_id, title="Same")

    note_id = await factories.insert_note(material_id=material_id)

    # the failed insert consumed number 2: sequences are not transactional
    assert (await _note_row(note_id))["note_number"] == 3


@pytest.mark.parametrize(
    "tags",
    [
        [],
        ["one"],
        ["b", "a", "b"],
        ["тег", "日本語", "with space", "quote'\"", "emoji-🙂"],
    ],
    ids=["empty", "single", "duplicates-keep-order", "unicode"],
)
async def test_insert_note_tags_round_trip_through_jsonb(material_id, tags):
    note_id = await factories.insert_note(material_id=material_id, tags=tags)

    assert (await _note_row(note_id))["tags"] == tags
    assert (await notes_db.get_note(note_id=note_id)).tags == set(tags)


async def test_insert_note_rejects_a_duplicate_title(material_id):
    await factories.insert_note(material_id=material_id, title="Unique title")

    with pytest.raises(database.AlreadyExistsException):
        await factories.insert_note(
            material_id=await factories.insert_material(),
            title="Unique title",
        )

    assert await factories.count_rows(models.Notes) == 1


async def test_insert_note_allows_several_notes_without_a_title(material_id):
    first = await factories.insert_note(material_id=material_id, title=None)
    second = await factories.insert_note(material_id=material_id, title=None)

    assert (await _note_row(first))["title"] is None
    assert (await _note_row(second))["title"] is None
    assert await factories.count_rows(models.Notes) == 2


async def test_insert_note_treats_titles_as_case_sensitive(material_id):
    await factories.insert_note(material_id=material_id, title="Title")
    await factories.insert_note(material_id=material_id, title="title")

    assert await factories.count_rows(models.Notes) == 2


@pytest.mark.parametrize(
    "content",
    [
        "Съешь ещё этих мягких французских булок, да выпей чаю.",
        "я" * 65_536,
        "line one\nline two\ttabbed",
        "",
    ],
    ids=["cyrillic", "max-length", "control-characters", "empty"],
)
async def test_insert_note_keeps_content_verbatim(material_id, content):
    note_id = await factories.insert_note(material_id=material_id, content=content)

    assert (await _note_row(note_id))["content"] == content


async def test_insert_note_rejects_content_over_the_column_limit(material_id):
    with pytest.raises(database.DatabaseException) as exc_info:
        await factories.insert_note(material_id=material_id, content="x" * 65_537)

    assert not isinstance(exc_info.value, database.AlreadyExistsException)
    assert await factories.count_rows(models.Notes) == 0


@pytest.mark.parametrize(
    ("length", "is_accepted"),
    [(256, True), (257, False)],
    ids=["at-the-limit", "one-over"],
)
async def test_insert_note_chapter_length_limit(material_id, length, is_accepted):
    chapter = "9" * length

    if is_accepted:
        note_id = await factories.insert_note(material_id=material_id, chapter=chapter)
        assert (await _note_row(note_id))["chapter"] == chapter
    else:
        with pytest.raises(database.DatabaseException):
            await factories.insert_note(material_id=material_id, chapter=chapter)
        assert await factories.count_rows(models.Notes) == 0


async def test_insert_note_accepts_an_unknown_material_current_behaviour():
    note_id = await factories.insert_note(material_id=MISSING_ID)

    assert (await _note_row(note_id))["material_id"] == MISSING_ID


async def test_update_note_changes_every_editable_column(material_id):
    other_material_id = await factories.insert_material()
    link_id = await factories.insert_note(material_id=material_id)
    note_id = await factories.insert_note(
        material_id=material_id,
        title="Before",
        content="Before.",
        chapter="1",
        page=1,
        tags=["old"],
    )
    before = await _note_row(note_id)

    await notes_db.update_note(
        note_id=note_id,
        material_id=other_material_id,
        link_id=link_id,
        title="After",
        content="После.",
        page=77,
        chapter="12",
        tags=["new", "тег"],
    )

    assert await _note_row(note_id) == {
        "note_id": note_id,
        "note_number": before["note_number"],
        "material_id": other_material_id,
        "link_id": link_id,
        "title": "After",
        "content": "После.",
        "added_at": before["added_at"],
        "chapter": "12",
        "page": 77,
        "tags": ["new", "тег"],
        "is_deleted": False,
        "sort_key": f"{other_material_id}$$0000000012$$0000000077$${note_id}",
    }


@pytest.mark.parametrize(
    ("chapter", "page"),
    [("2", 1), ("1", 2), ("10", 10)],
    ids=["chapter-changed", "page-changed", "both-changed"],
)
async def test_update_note_recomputes_the_sort_key(material_id, chapter, page):
    note_id = await factories.insert_note(material_id=material_id, chapter="1", page=1)
    old_sort_key = (await _note_row(note_id))["sort_key"]

    await notes_db.update_note(
        note_id=note_id,
        material_id=material_id,
        link_id=None,
        title=None,
        content="Note content.",
        page=page,
        chapter=chapter,
        tags=[],
    )

    new_sort_key = (await _note_row(note_id))["sort_key"]
    assert new_sort_key != old_sort_key
    assert new_sort_key == sort_keys.note_sort_key(
        material_id=material_id,
        chapter=chapter,
        page=page,
        note_id=note_id,
    )


async def test_update_note_clears_optional_columns(material_id):
    link_id = await factories.insert_note(material_id=material_id)
    note_id = await factories.insert_note(
        material_id=material_id,
        title="Title",
        link_id=link_id,
        tags=["tag"],
    )

    await notes_db.update_note(
        note_id=note_id,
        material_id=material_id,
        link_id=None,
        title=None,
        content="Note content.",
        page=1,
        chapter="1",
        tags=[],
    )

    row = await _note_row(note_id)
    assert (row["title"], row["link_id"], row["tags"]) == (None, None, [])


async def test_update_note_raises_not_found_for_a_missing_id(material_id):
    untouched = await factories.insert_note(material_id=material_id)
    before = await _note_row(untouched)

    with pytest.raises(database.NotFoundException, match=str(MISSING_ID)):
        await notes_db.update_note(
            note_id=MISSING_ID,
            material_id=material_id,
            link_id=None,
            title=None,
            content="Changed.",
            page=5,
            chapter="5",
            tags=[],
        )

    assert await _note_row(untouched) == before


async def test_update_note_rejects_the_title_of_another_note(material_id):
    await factories.insert_note(material_id=material_id, title="Taken")
    note_id = await factories.insert_note(material_id=material_id, title="Mine")

    with pytest.raises(database.AlreadyExistsException):
        await notes_db.update_note(
            note_id=note_id,
            material_id=material_id,
            link_id=None,
            title="Taken",
            content="Note content.",
            page=1,
            chapter="1",
            tags=[],
        )

    assert (await _note_row(note_id))["title"] == "Mine"


async def test_update_note_keeps_a_deleted_note_deleted(material_id):
    note_id = await factories.insert_note(material_id=material_id)
    await notes_db.delete_note(note_id=note_id)

    await notes_db.update_note(
        note_id=note_id,
        material_id=material_id,
        link_id=None,
        title=None,
        content="Edited while deleted.",
        page=1,
        chapter="1",
        tags=[],
    )

    row = await _note_row(note_id)
    assert row["is_deleted"] is True
    assert row["content"] == "Edited while deleted."


async def test_delete_note_hides_it_from_every_read(material_id):
    kept = await factories.insert_note(material_id=material_id)
    deleted = await factories.insert_note(material_id=material_id)

    await notes_db.delete_note(note_id=deleted)

    assert (await _note_row(deleted))["is_deleted"] is True
    with pytest.raises(database.NotFoundException):
        await notes_db.get_note(note_id=deleted)
    assert [note.note_id for note in await notes_db.get_notes()] == [kept]
    assert await notes_db.get_all_notes_count() == {material_id: 1}


async def test_delete_note_of_the_only_note_empties_the_material_reads(material_id):
    note_id = await factories.insert_note(material_id=material_id)

    await notes_db.delete_note(note_id=note_id)

    assert await notes_db.get_notes(material_id=material_id) == []
    assert await notes_db.get_all_notes_count() == {}
    assert await notes_db.get_material_with_notes_titles() == {}


async def test_restore_note_makes_it_visible_again(material_id):
    note_id = await factories.insert_note(material_id=material_id)
    await notes_db.delete_note(note_id=note_id)

    await notes_db.restore_note(note_id=note_id)

    assert (await _note_row(note_id))["is_deleted"] is False
    assert (await notes_db.get_note(note_id=note_id)).note_id == note_id
    assert await notes_db.get_all_notes_count() == {material_id: 1}


async def test_delete_note_twice_is_idempotent(material_id):
    note_id = await factories.insert_note(material_id=material_id)

    await notes_db.delete_note(note_id=note_id)
    await notes_db.delete_note(note_id=note_id)

    assert (await _note_row(note_id))["is_deleted"] is True


async def test_restore_note_that_is_not_deleted_is_idempotent(material_id):
    note_id = await factories.insert_note(material_id=material_id)

    await notes_db.restore_note(note_id=note_id)
    await notes_db.restore_note(note_id=note_id)

    assert (await _note_row(note_id))["is_deleted"] is False


@pytest.mark.parametrize(
    "change",
    [notes_db.delete_note, notes_db.restore_note],
    ids=["delete", "restore"],
)
async def test_delete_and_restore_raise_not_found_for_a_missing_id(material_id, change):
    note_id = await factories.insert_note(material_id=material_id)

    with pytest.raises(database.NotFoundException, match=str(MISSING_ID)):
        await change(note_id=MISSING_ID)

    assert (await _note_row(note_id))["is_deleted"] is False


async def test_get_note_returns_the_stored_note(material_id):
    link_id = await factories.insert_note(material_id=material_id)
    note_id = await factories.insert_note(
        material_id=material_id,
        link_id=link_id,
        title="Title",
        content="Content.",
        chapter="Глава 4",
        page=8,
        tags=["a", "b"],
    )
    row = await _note_row(note_id)

    note = await notes_db.get_note(note_id=note_id)

    assert note == notes_db.Note(
        note_id=note_id,
        link_id=link_id,
        material_id=material_id,
        title="Title",
        content="Content.",
        added_at=row["added_at"],
        chapter="Глава 4",
        page=8,
        tags={"a", "b"},
        is_deleted=False,
        note_number=2,
        links_count=0,
    )


async def test_get_note_counts_only_live_notes_linking_to_it(material_id):
    target = await factories.insert_note(material_id=material_id)
    await factories.insert_note(material_id=material_id, link_id=target)
    await factories.insert_note(
        material_id=await factories.insert_material(),
        link_id=target,
    )
    deleted_link = await factories.insert_note(material_id=material_id, link_id=target)
    await notes_db.delete_note(note_id=deleted_link)

    note = await notes_db.get_note(note_id=target)

    assert note.links_count == 2


async def test_get_note_raises_not_found_for_a_missing_id(material_id):
    await factories.insert_note(material_id=material_id)

    with pytest.raises(database.NotFoundException, match=str(MISSING_ID)):
        await notes_db.get_note(note_id=MISSING_ID)


async def test_get_note_raises_not_found_for_a_deleted_note(material_id):
    note_id = await factories.insert_note(material_id=material_id)
    await notes_db.delete_note(note_id=note_id)

    with pytest.raises(database.NotFoundException):
        await notes_db.get_note(note_id=note_id)


@pytest.mark.parametrize("null", [sa.null(), None], ids=["sql-null", "json-null"])
async def test_get_note_reads_a_note_without_tags(material_id, null):
    note_id = await helpers.insert_raw_note(material_id=material_id, tags=null)

    note = await notes_db.get_note(note_id=note_id)

    assert note.tags == set()


async def test_get_notes_lists_notes_without_tags(material_id):
    with_tags = await factories.insert_note(material_id=material_id, tags=["tag"])
    without_tags = await helpers.insert_raw_note(material_id=material_id, tags=sa.null())

    notes = await notes_db.get_notes()

    assert [note.note_id for note in notes] == [with_tags, without_tags]


async def test_get_notes_returns_live_notes_in_note_number_order(material_id):
    other_material_id = await factories.insert_material()
    first = await factories.insert_note(material_id=material_id, chapter="9", page=9)
    second = await factories.insert_note(material_id=other_material_id)
    deleted = await factories.insert_note(material_id=material_id)
    third = await factories.insert_note(material_id=material_id, chapter="1", page=1)
    await notes_db.delete_note(note_id=deleted)

    notes = await notes_db.get_notes()

    assert [note.note_id for note in notes] == [first, second, third]
    assert [note.note_number for note in notes] == [1, 2, 4]


@pytest.mark.parametrize("as_type", [uuid.UUID, str], ids=["uuid", "str"])
async def test_get_notes_filters_by_material(material_id, as_type):
    other_material_id = await factories.insert_material()
    mine = await factories.insert_note(material_id=material_id)
    await factories.insert_note(material_id=other_material_id)

    notes = await notes_db.get_notes(material_id=as_type(str(material_id)))

    assert [note.note_id for note in notes] == [mine]
    assert notes[0].links_count == 0


async def test_get_notes_of_a_material_without_notes_is_empty(material_id):
    await factories.insert_note(material_id=material_id)

    assert await notes_db.get_notes(material_id=MISSING_ID) == []


async def test_get_notes_on_an_empty_database_is_empty():
    assert await notes_db.get_notes() == []


async def test_get_all_notes_count_groups_live_notes_by_material(material_id):
    other_material_id = await factories.insert_material()
    empty_material_id = await factories.insert_material()
    for _ in range(3):
        await factories.insert_note(material_id=material_id)
    deleted = await factories.insert_note(material_id=material_id)
    await notes_db.delete_note(note_id=deleted)
    await factories.insert_note(material_id=other_material_id)

    counts = await notes_db.get_all_notes_count()

    assert counts == {material_id: 3, other_material_id: 1}
    assert empty_material_id not in counts


async def test_get_all_notes_count_on_an_empty_database_is_empty():
    assert await notes_db.get_all_notes_count() == {}


async def test_get_material_types_maps_every_material():
    ids = {
        material_type: await factories.insert_material(material_type=material_type)
        for material_type in enums.MaterialTypesEnum
    }

    types = await notes_db.get_material_types()

    assert types == {
        material_id: material_type for material_type, material_id in ids.items()
    }


async def test_get_material_types_on_an_empty_database_is_empty():
    assert await notes_db.get_material_types() == {}


async def test_get_material_titles_maps_every_material():
    first = await factories.insert_material(title="Война и мир")
    second = await factories.insert_material(title="B" * 256)

    assert await notes_db.get_material_titles() == {
        first: "Война и мир",
        second: "B" * 256,
    }


async def test_get_material_titles_on_an_empty_database_is_empty():
    assert await notes_db.get_material_titles() == {}


async def test_get_material_with_notes_titles_lists_only_materials_with_live_notes():
    with_notes = await factories.insert_material(title="With notes")
    only_deleted = await factories.insert_material(title="Only deleted notes")
    await factories.insert_material(title="No notes")
    await factories.insert_note(material_id=with_notes)
    await factories.insert_note(material_id=with_notes)
    deleted = await factories.insert_note(material_id=only_deleted)
    await notes_db.delete_note(note_id=deleted)
    await factories.insert_note(material_id=MISSING_ID)

    titles = await notes_db.get_material_with_notes_titles()

    assert titles == {with_notes: "With notes"}


async def test_get_material_with_notes_titles_on_an_empty_database_is_empty():
    assert await notes_db.get_material_with_notes_titles() == {}


async def test_get_tags_returns_the_union_of_all_note_tags(material_id):
    await factories.insert_note(material_id=material_id, tags=["a", "b"])
    await factories.insert_note(
        material_id=await factories.insert_material(),
        tags=["b", "тег"],
    )
    await factories.insert_note(material_id=material_id, tags=[])
    await helpers.insert_raw_note(material_id=material_id, tags=sa.null())

    assert await notes_db._get_tags() == {"a", "b", "тег"}


async def test_get_tags_on_an_empty_database_is_empty():
    assert await notes_db._get_tags() == set()


async def test_get_tags_includes_tags_of_deleted_notes_current_behaviour(material_id):
    note_id = await factories.insert_note(material_id=material_id, tags=["gone"])
    await notes_db.delete_note(note_id=note_id)

    assert await notes_db._get_tags() == {"gone"}


async def test_get_tags_ignores_a_json_null(material_id):
    await factories.insert_note(material_id=material_id, tags=["a"])
    await helpers.insert_raw_note(material_id=material_id, tags=None)

    assert await notes_db._get_tags() == {"a"}


@pytest.mark.parametrize("as_type", [uuid.UUID, str], ids=["uuid", "str"])
async def test_get_material_tags_orders_by_frequency(material_id, as_type):
    await factories.insert_note(material_id=material_id, tags=["rare", "common", "usual"])
    await factories.insert_note(material_id=material_id, tags=["common", "usual"])
    await factories.insert_note(material_id=material_id, tags=["common"])
    await factories.insert_note(material_id=material_id, tags=[])
    await factories.insert_note(
        material_id=await factories.insert_material(),
        tags=["foreign"],
    )

    tags = await notes_db._get_material_tags(as_type(str(material_id)))

    assert tags == ["common", "usual", "rare"]


async def test_get_material_tags_of_a_material_without_notes_is_empty(material_id):
    await factories.insert_note(material_id=material_id, tags=["tag"])

    assert await notes_db._get_material_tags(MISSING_ID) == []


@pytest.mark.parametrize("no_material", [None, ""], ids=["none", "empty-string"])
async def test_get_sorted_tags_without_a_material_sorts_all_tags(
    material_id,
    no_material,
):
    await factories.insert_note(material_id=material_id, tags=["b", "c"])
    await factories.insert_note(
        material_id=await factories.insert_material(),
        tags=["a", "c"],
    )

    assert await notes_db.get_sorted_tags(material_id=no_material) == ["a", "b", "c"]


async def test_get_sorted_tags_puts_the_material_tags_first(material_id):
    await factories.insert_note(material_id=material_id, tags=["zeta", "mid"])
    await factories.insert_note(material_id=material_id, tags=["zeta"])
    other_material_id = await factories.insert_material()
    await factories.insert_note(
        material_id=other_material_id,
        tags=["alpha", "zeta", "beta"],
    )

    tags = await notes_db.get_sorted_tags(material_id=material_id)

    assert tags == ["zeta", "mid", "alpha", "beta"]


async def test_get_sorted_tags_of_an_unknown_material_sorts_all_tags(material_id):
    await factories.insert_note(material_id=material_id, tags=["b", "a"])

    assert await notes_db.get_sorted_tags(material_id=MISSING_ID) == ["a", "b"]


async def test_get_sorted_tags_on_an_empty_database_is_empty(material_id):
    assert await notes_db.get_sorted_tags(material_id=None) == []
    assert await notes_db.get_sorted_tags(material_id=material_id) == []


async def test_get_possible_links_orders_by_shared_tags(material_id):
    note_id = await factories.insert_note(material_id=material_id, tags=["a", "b", "c"])
    one_shared = await factories.insert_note(material_id=material_id, tags=["a", "x"])
    three_shared = await factories.insert_note(
        material_id=await factories.insert_material(),
        tags=["a", "b", "c", "y"],
    )
    two_shared = await factories.insert_note(material_id=material_id, tags=["c", "b"])
    await factories.insert_note(material_id=material_id, tags=["x", "y"])
    await factories.insert_note(material_id=material_id, tags=[])
    deleted = await factories.insert_note(material_id=material_id, tags=["a", "b", "c"])
    await notes_db.delete_note(note_id=deleted)

    links = await notes_db.get_possible_links(note_id, {"a", "b", "c"})

    assert [link.note_id for link in links] == [three_shared, two_shared, one_shared]
    assert [link.links_count for link in links] == [None, None, None]


async def test_get_possible_links_uses_the_stored_tags_not_the_passed_ones(material_id):
    note_id = await factories.insert_note(material_id=material_id, tags=["stored"])
    match = await factories.insert_note(material_id=material_id, tags=["stored"])
    await factories.insert_note(material_id=material_id, tags=["passed"])

    links = await notes_db.get_possible_links(note_id, {"passed"})

    assert [link.note_id for link in links] == [match]


@pytest.mark.parametrize("tags", [[], sa.null()], ids=["empty-tags", "null-tags"])
async def test_get_possible_links_of_a_note_without_tags_is_empty(material_id, tags):
    note_id = await helpers.insert_raw_note(material_id=material_id, tags=tags)
    await factories.insert_note(material_id=material_id, tags=["a"])

    assert await notes_db.get_possible_links(note_id, set()) == []


async def test_get_possible_links_of_a_missing_note_is_empty(material_id):
    await factories.insert_note(material_id=material_id, tags=["a"])

    assert await notes_db.get_possible_links(MISSING_ID, {"a"}) == []


async def test_get_possible_links_cannot_be_injected_through_the_note_id(material_id):
    await factories.insert_note(material_id=material_id, tags=["a"])
    await factories.insert_note(material_id=material_id, tags=["b"])

    # the id is also a bound UUID parameter, so a forged string never reaches the server
    with pytest.raises(
        database.DatabaseException,
        match="invalid input syntax for type uuid",
    ):
        await notes_db.get_possible_links("x' OR '1'='1", {"a"})  # type: ignore[arg-type]


async def _search(**kwargs) -> list[uuid.UUID]:
    filters = {
        "material_id": None,
        "query": None,
        "tags": set(),
        "note_ids": None,
        **kwargs,
    }
    page = await notes_db.search_notes_page(**filters, params=PageParams(page_size=100))

    assert page.next_token is None
    assert page.total_count == len(page.items)
    return [note.note_id for note in page.items]


@pytest.fixture
async def notes(material_id) -> dict[str, uuid.UUID]:
    """Five live notes over two materials plus a deleted one, keyed by a short name."""
    other_material_id = await factories.insert_material()
    created = {
        "ab": await factories.insert_note(
            material_id=material_id,
            page=1,
            tags=["a", "b"],
        ),
        "a": await factories.insert_note(material_id=material_id, page=2, tags=["a"]),
        "none": await factories.insert_note(material_id=material_id, page=3, tags=[]),
        "other_ab": await factories.insert_note(
            material_id=other_material_id,
            page=1,
            tags=["b", "a", "c"],
        ),
        "other_c": await factories.insert_note(
            material_id=other_material_id,
            page=2,
            tags=["c"],
        ),
        "deleted": await factories.insert_note(
            material_id=material_id,
            page=4,
            tags=["a", "b"],
        ),
    }
    await notes_db.delete_note(note_id=created["deleted"])
    return created


SEARCH_CASES = {
    "no-filters": ({}, {"ab", "a", "none", "other_ab", "other_c"}),
    "material": ({"material": "mine"}, {"ab", "a", "none"}),
    "material-as-str": ({"material": "mine-str"}, {"ab", "a", "none"}),
    "empty-material-string": (
        {"material": ""},
        {"ab", "a", "none", "other_ab", "other_c"},
    ),
    "unknown-material": ({"material": "missing"}, set()),
    "one-tag": ({"tags": {"a"}}, {"ab", "a", "other_ab"}),
    "all-tags-required": ({"tags": {"a", "b"}}, {"ab", "other_ab"}),
    "unknown-tag": ({"tags": {"zzz"}}, set()),
    "note-ids": ({"ids": ["a", "other_c"]}, {"a", "other_c"}),
    "note-ids-empty": ({"ids": []}, set()),
    "note-ids-with-deleted-and-missing": ({"ids": ["ab", "deleted", "missing"]}, {"ab"}),
    "material-and-tags": ({"material": "mine", "tags": {"b"}}, {"ab"}),
    "material-and-ids": ({"material": "mine", "ids": ["a", "other_c"]}, {"a"}),
    "tags-and-ids": ({"tags": {"c"}, "ids": ["other_ab", "ab"]}, {"other_ab"}),
    "material-tags-ids": (
        {"material": "mine", "tags": {"a"}, "ids": ["ab", "none", "other_ab"]},
        {"ab"},
    ),
    "query-alone-does-not-filter": (
        {"query": "anything"},
        {"ab", "a", "none", "other_ab", "other_c"},
    ),
    "query-with-ids": ({"query": "found", "ids": ["none"]}, {"none"}),
}


@pytest.mark.parametrize("case", SEARCH_CASES, ids=list(SEARCH_CASES))
async def test_search_notes_page_filters(material_id, notes, case):
    filters, expected = SEARCH_CASES[case]
    materials = {
        "mine": material_id,
        "mine-str": str(material_id),
        "missing": MISSING_ID,
        "": "",
    }
    kwargs: dict = {}
    if "material" in filters:
        kwargs["material_id"] = materials[filters["material"]]
    if "tags" in filters:
        kwargs["tags"] = filters["tags"]
    if "ids" in filters:
        kwargs["note_ids"] = [notes.get(name, MISSING_ID) for name in filters["ids"]]
    if "query" in filters:
        kwargs["query"] = filters["query"]

    found = await _search(**kwargs)

    assert set(found) == {notes[name] for name in expected}
    assert len(found) == len(expected)


async def test_search_notes_page_returns_full_notes_with_links_count(material_id):
    target = await factories.insert_note(
        material_id=material_id,
        page=1,
        tags=["t"],
        title="T",
    )
    await factories.insert_note(material_id=material_id, page=2, link_id=target)
    row = await _note_row(target)

    page = await notes_db.search_notes_page(
        material_id=material_id,
        query=None,
        tags={"t"},
        note_ids=None,
        params=PageParams(),
    )

    assert page.items == [
        notes_db.Note(
            note_id=target,
            link_id=None,
            material_id=material_id,
            title="T",
            content="Note content.",
            added_at=row["added_at"],
            chapter="1",
            page=1,
            tags={"t"},
            is_deleted=False,
            note_number=1,
            links_count=1,
        ),
    ]
    assert page.total_count == 1
    assert page.next_token is None


async def test_search_notes_page_accepts_note_ids_as_a_set(material_id, notes):
    found = await _search(note_ids={notes["a"], notes["none"]})

    assert set(found) == {notes["a"], notes["none"]}


async def test_search_notes_page_with_a_tag_filter_skips_notes_with_null_tags(
    material_id,
):
    tagged = await factories.insert_note(material_id=material_id, tags=["a"])
    await helpers.insert_raw_note(material_id=material_id, tags=sa.null())

    assert await _search(tags={"a"}) == [tagged]


async def test_search_notes_page_on_an_empty_database_is_empty():
    page = await notes_db.search_notes_page(
        material_id=None,
        query=None,
        tags=set(),
        note_ids=None,
        params=PageParams(),
    )

    assert (page.items, page.total_count, page.next_token) == ([], 0, None)


async def _chapters(**kwargs) -> dict[uuid.UUID, list[str]]:
    filters = {"material_id": None, "tags": set(), "note_ids": None, **kwargs}
    return await notes_db.get_distinct_chapters(**filters)


async def test_get_distinct_chapters_follow_the_listing_order(material_id):
    other_material_id = await factories.insert_material()
    for chapter, page in [
        ("10", 1),
        ("2", 5),
        ("2", 1),
        ("Глава 1", 9),
        ("no digits", 3),
    ]:
        await factories.insert_note(material_id=material_id, chapter=chapter, page=page)
    await factories.insert_note(material_id=other_material_id, chapter="3")
    deleted = await factories.insert_note(material_id=other_material_id, chapter="1")
    await notes_db.delete_note(note_id=deleted)

    chapters = await _chapters()

    assert isinstance(chapters, defaultdict)
    assert chapters == {
        material_id: ["no digits", "Глава 1", "2", "10"],
        other_material_id: ["3"],
    }


async def test_get_distinct_chapters_keeps_chapters_with_equal_numbers_apart(material_id):
    await factories.insert_note(material_id=material_id, chapter="1", page=1)
    await factories.insert_note(material_id=material_id, chapter="Chapter 1", page=2)

    assert await _chapters() == {material_id: ["1", "Chapter 1"]}


async def test_get_distinct_chapters_apply_the_search_filters(material_id, notes):
    other_material_id = (await _note_row(notes["other_c"]))["material_id"]
    await factories.insert_note(material_id=material_id, chapter="7", tags=["a"])

    assert await _chapters(material_id=material_id) == {material_id: ["1", "7"]}
    assert await _chapters(tags={"c"}) == {other_material_id: ["1"]}
    assert await _chapters(note_ids=[notes["a"]]) == {material_id: ["1"]}
    assert await _chapters(note_ids=[]) == {}


async def test_get_distinct_chapters_on_an_empty_database_is_empty():
    assert await _chapters() == {}


@pytest.fixture
async def linked_notes(material_id) -> dict[str, uuid.UUID]:
    """root <- child <- grandchild inside one material, foreign -> root from another one."""
    other_material_id = await factories.insert_material()
    root = await factories.insert_note(
        material_id=material_id,
        content="Root &lt;note&gt;.",
    )
    child = await factories.insert_note(material_id=material_id, link_id=root)
    grandchild = await factories.insert_note(material_id=material_id, link_id=child)
    foreign = await factories.insert_note(material_id=other_material_id, link_id=root)
    lonely = await factories.insert_note(material_id=material_id)
    return {
        "root": root,
        "child": child,
        "grandchild": grandchild,
        "foreign": foreign,
        "lonely": lonely,
    }


async def _notes_by_id() -> dict[uuid.UUID, notes_db.Note]:
    return {note.note_id: note for note in await notes_db.get_notes()}


def _edges(graph, names: dict[str, uuid.UUID]) -> set[tuple[str, str]]:
    by_id = {str(note_id): name for name, note_id in names.items()}
    return {(by_id[source], by_id[target]) for source, target in graph.edges}


@pytest.mark.parametrize("start", ["root", "child", "grandchild", "foreign"])
async def test_link_notes_collects_the_whole_linked_group_from_any_note(
    linked_notes,
    start,
):
    notes = await _notes_by_id()

    graph = notes_db.link_notes(note_id=linked_notes[start], notes=notes)

    assert set(graph.nodes) == {
        str(linked_notes[name]) for name in ("root", "child", "grandchild", "foreign")
    }
    assert _edges(graph, linked_notes) == {
        ("child", "root"),
        ("grandchild", "child"),
        ("foreign", "root"),
    }
    assert graph.nodes[str(linked_notes[start])]["color"] == "black"


async def test_link_notes_of_a_note_without_links_is_a_single_node(
    linked_notes,
    material_id,
):
    notes = await _notes_by_id()

    graph = notes_db.link_notes(note_id=linked_notes["lonely"], notes=notes)

    assert dict(graph.nodes) == {
        str(linked_notes["lonely"]): {
            "color": "black",
            "title": "Note content.",
            "material_id": str(material_id),
            "note_number": 5,
            "label": "Note content....",
        },
    }
    assert list(graph.edges) == []


async def test_link_all_notes_links_every_note_read_from_the_database(linked_notes):
    notes = await notes_db.get_notes()

    graph = notes_db.link_all_notes(notes)

    assert set(graph.nodes) == {str(note_id) for note_id in linked_notes.values()}
    assert _edges(graph, linked_notes) == {
        ("child", "root"),
        ("grandchild", "child"),
        ("foreign", "root"),
    }
    assert graph.nodes[str(linked_notes["root"])]["title"] == "Root <note>."


async def test_link_all_notes_of_an_empty_database_is_an_empty_graph():
    graph = notes_db.link_all_notes(await notes_db.get_notes())

    assert (len(graph.nodes), len(graph.edges)) == (0, 0)


async def test_create_material_graph_highlights_notes_of_other_materials(
    linked_notes,
    material_id,
):
    notes = await _notes_by_id()
    material_notes = {
        str(note.note_id) for note in notes.values() if note.material_id == material_id
    }

    graph = notes_db.create_material_graph(
        material_id=material_id,
        material_notes={uuid.UUID(note_id) for note_id in material_notes},
        notes=notes,
    )

    assert set(graph.nodes) == {str(note_id) for note_id in linked_notes.values()}
    colors = {
        name: graph.nodes[str(note_id)].get("color")
        for name, note_id in linked_notes.items()
    }
    assert colors == {
        "root": None,
        "child": None,
        "grandchild": None,
        "foreign": "black",
        "lonely": None,
    }


async def test_create_material_graph_of_a_material_without_notes_is_empty(
    linked_notes, material_id
):
    graph = notes_db.create_material_graph(
        material_id=material_id,
        material_notes=set(),
        notes=await _notes_by_id(),
    )

    assert (len(graph.nodes), len(graph.edges)) == (0, 0)


async def test_create_graphic_renders_the_graph_of_stored_notes(linked_notes):
    graph = notes_db.link_all_notes(await notes_db.get_notes())

    html = notes_db.create_graphic(graph, height="80vh")

    assert html.lstrip().startswith("<html>")
    for note_id in linked_notes.values():
        assert str(note_id) in html
    assert '"hover": true' in html


async def test_stored_note_renders_its_derived_fields(material_id):
    target = await factories.insert_note(material_id=material_id)
    note_id = await factories.insert_note(
        material_id=material_id,
        link_id=target,
        content="a &lt; b, " + "x" * 60,
        chapter="Глава 12",
        tags=["tag", "longer_tag"],
    )

    note = await notes_db.get_note(note_id=note_id)

    assert note.content_md == str(note) == "a < b, " + "x" * 60
    assert note.content_html == "a &lt; b, " + "x" * 60
    assert note.short_content == ("a < b, " + "x" * 43) + "..."
    assert note.info == (
        f"ID: {note_id}\nNumber: 2\nMaterial ID: {material_id}\n\n" + "a < b, " + "x" * 60
    )
    assert note.chapter_int == 12
    assert note.tags_str == "#longer_tag #tag"
    assert note.tags_html == (
        '<a href=http://tracker.test/notes/?tags_query=longer_tag target="_blank">#longer_tag</a> '
        '<a href=http://tracker.test/notes/?tags_query=tag target="_blank">#tag</a>'
    )
    assert note.link_html == (
        f'<a class="link-ref" href=http://tracker.test/notes/{target} '
        f'target="_blank">[[{target}]]</a>'
    )
    assert note.model_dump()["added_at"] == note.added_at.strftime("%Y-%m-%d %H:%M:%S")
    note.highlight("a &lt; b", "**a &lt; b**")
    assert note.content.startswith("**a &lt; b**, ")


async def test_stored_note_without_a_link_has_no_link_html(material_id):
    note_id = await factories.insert_note(material_id=material_id)

    note = await notes_db.get_note(note_id=note_id)

    assert note.link_html == ""
    assert note.tags_str == ""


async def test_add_links_to_follows_the_chain_of_links_and_stops_on_a_cycle(material_id):
    first = await factories.insert_note(material_id=material_id)
    second = await factories.insert_note(material_id=material_id, link_id=first)
    third = await factories.insert_note(material_id=material_id, link_id=second)
    await notes_db.update_note(
        note_id=first,
        material_id=material_id,
        link_id=third,
        title=None,
        content="Note content.",
        page=1,
        chapter="1",
        tags=[],
    )
    notes = await _notes_by_id()
    graph = notes_db.nx.DiGraph()
    added: set[uuid.UUID] = set()

    notes_db._add_links_to(graph, notes, third, added)

    assert added == {first, second, third}
    assert set(graph.edges) == {
        (str(third), str(second)),
        (str(second), str(first)),
        (str(first), str(third)),
    }


async def test_note_accepts_tags_serialized_as_a_json_string(material_id):
    note_id = await factories.insert_note(material_id=material_id, tags=["a", "b"])
    row = await _note_row(note_id)

    del row["sort_key"]

    note = notes_db.Note.model_validate({**row, "tags": '["a", "b"]'})

    assert note.tags == {"a", "b"}


# is_link_cyclic, count_links_to


async def _set_link(note_id: uuid.UUID, link_id: uuid.UUID | None) -> None:
    stmt = (
        models.Notes.update()
        .values(link_id=link_id)
        .where(models.Notes.c.note_id == note_id)
    )
    async with database.session() as ses:
        await ses.execute(stmt)


async def _chain(material_id: uuid.UUID, length: int) -> list[uuid.UUID]:
    """Notes n0 <- n1 <- ... <- n(length-1): every note links to the previous one."""
    note_ids = [await factories.insert_note(material_id=material_id)]
    for _ in range(length - 1):
        note_ids.append(
            await factories.insert_note(material_id=material_id, link_id=note_ids[-1])
        )
    return note_ids


async def test_is_link_cyclic_for_a_self_link(material_id):
    note_id = await factories.insert_note(material_id=material_id)

    assert await notes_db.is_link_cyclic(note_id=note_id, link_id=note_id) is True


@pytest.mark.parametrize(
    "length", [2, 3, 4], ids=["cycle-of-2", "cycle-of-3", "cycle-of-4"]
)
async def test_is_link_cyclic_when_the_target_leads_back(material_id, length):
    note_ids = await _chain(material_id, length)

    # the first note of the chain would link to the last one, which leads back to it
    assert (
        await notes_db.is_link_cyclic(note_id=note_ids[0], link_id=note_ids[-1]) is True
    )


async def test_is_link_cyclic_is_false_for_a_chain_without_the_note(material_id):
    note_ids = await _chain(material_id, 3)
    other = await factories.insert_note(material_id=material_id)

    assert await notes_db.is_link_cyclic(note_id=other, link_id=note_ids[-1]) is False


async def test_is_link_cyclic_is_false_for_a_target_without_a_link(material_id):
    note_id = await factories.insert_note(material_id=material_id)
    target = await factories.insert_note(material_id=material_id)

    assert await notes_db.is_link_cyclic(note_id=note_id, link_id=target) is False


async def test_is_link_cyclic_is_false_for_an_unknown_target(material_id):
    note_id = await factories.insert_note(material_id=material_id)

    assert await notes_db.is_link_cyclic(note_id=note_id, link_id=uuid.uuid4()) is False


async def test_is_link_cyclic_terminates_on_a_cycle_already_in_the_data(material_id):
    first, second = await _chain(material_id, 2)
    await _set_link(first, second)
    other = await factories.insert_note(material_id=material_id)

    assert await notes_db.is_link_cyclic(note_id=other, link_id=first) is False


async def test_is_link_cyclic_follows_deleted_notes(material_id):
    first, second, third = await _chain(material_id, 3)
    await notes_db.delete_note(note_id=second)

    assert await notes_db.is_link_cyclic(note_id=first, link_id=third) is True


async def test_count_links_to_counts_only_live_linking_notes(material_id):
    target = await factories.insert_note(material_id=material_id)
    await factories.insert_note(material_id=material_id, link_id=target)
    deleted = await factories.insert_note(material_id=material_id, link_id=target)
    await factories.insert_note(material_id=material_id, link_id=target)
    await factories.insert_note(material_id=material_id)
    await notes_db.delete_note(note_id=deleted)

    assert await notes_db.count_links_to(note_id=target) == 2


async def test_count_links_to_a_note_without_links_is_zero(material_id):
    target = await factories.insert_note(material_id=material_id)

    assert await notes_db.count_links_to(note_id=target) == 0
