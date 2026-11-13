import logging
import uuid

import pytest

from migrations import update_notes_format
from tests.integration import factories
from tracker.common import database
from tracker.models import models
from tracker.notes import db as notes_db


LINK_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


def _note(
    content: str,
    *,
    tags: set[str] | None = None,
    link_id: uuid.UUID | None = None,
):
    return notes_db.Note(
        note_id=uuid.uuid4(),
        link_id=link_id,
        material_id=uuid.uuid4(),
        content=content,
        added_at=database.utcnow(),
        chapter="1",
        page=1,
        tags=tags or set(),
        is_deleted=False,
        note_number=1,
    )


@pytest.mark.parametrize(
    ("text", "tags", "expected"),
    [
        ("Text #tag", {"tag"}, "Text "),
        ("Text #tag #other", {"tag"}, "Text  #other"),
        ("#tagged stays", {"tag"}, "#tagged stays"),
        ("word#tag stays", {"tag"}, "word#tag stays"),
        ("Текст #тег.", {"тег"}, "Текст ."),
        ("No tags", set(), "No tags"),
    ],
    ids=["one", "unknown-kept", "longer-word-kept", "glued-kept", "cyrillic", "no-tags"],
)
def test_delete_tags(text, tags, expected):
    assert update_notes_format._delete_tags(text, tags) == expected


@pytest.mark.parametrize(
    ("text", "link_id", "expected"),
    [
        (f"Text [[{LINK_ID}]]", LINK_ID, "Text "),
        (f"Text [[{LINK_ID}]]", str(LINK_ID), "Text "),
        (f"Text [[{LINK_ID}]]", None, f"Text [[{LINK_ID}]]"),
        (f"Text [[{LINK_ID}]]", uuid.UUID(int=1), f"Text [[{LINK_ID}]]"),
    ],
    ids=["uuid", "str", "no-link", "other-link"],
)
def test_delete_link(text, link_id, expected):
    assert update_notes_format._delete_link(text, link_id) == expected


def test_dereplace_new_lines():
    assert update_notes_format._dereplace_new_lines("a<br>b<br/>c<BR>") == "a\nb\nc<BR>"


@pytest.mark.parametrize(
    ("string", "expected"),
    [("", ""), ("Text", "Text."), ("Text.", "Text."), ("Why?", "Why?"), ("Wow!", "Wow!")],
    ids=["empty", "no-ending", "dot", "question", "exclamation"],
)
def test_add_dot(string, expected):
    assert update_notes_format.add_dot(string) == expected


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (f"First<br/>second #tag [[{LINK_ID}]]", "First\nsecond."),
        ("  Padded text .  ", "Padded text."),
        ("Already fine.", "Already fine."),
        ("", ""),
    ],
    ids=["link-tag-newline", "space-before-dot", "unchanged", "empty"],
)
def test_format_content_cleans_and_ends_with_a_dot(content, expected):
    assert update_notes_format._format_content(content, {"tag"}, LINK_ID) == expected


@pytest.mark.parametrize(("content", "expected"), [("Why?", "Why."), ("Wow !", "Wow.")])
def test_format_content_replaces_a_final_question_or_exclamation_mark_current_behaviour(
    content,
    expected,
):
    assert update_notes_format._format_content(content, set(), None) == expected


def test_format_content_demarks_html_entities():
    note = _note("a &lt; b &gt; c #tag", tags={"tag"})

    assert update_notes_format.format_content(note) == "a < b > c."


def test_format_content_warns_when_hashes_and_tags_disagree(caplog):
    note = _note("Issue #42 #tag", tags={"tag"})

    with caplog.at_level(logging.WARNING):
        content = update_notes_format.format_content(note)

    assert content == "Issue #42."
    assert [record.levelname for record in caplog.records] == ["WARNING", "WARNING"]
    assert str(note.note_id) in caplog.records[0].getMessage()
    assert caplog.records[1].getMessage() == "Clean content: 'Issue #42.'"


def test_format_content_does_not_warn_when_every_hash_is_a_tag(caplog):
    note = _note("Text #one #two", tags={"one", "two"})

    with caplog.at_level(logging.WARNING):
        update_notes_format.format_content(note)

    assert caplog.records == []


async def test_get_all_notes_returns_the_live_notes():
    material_id = await factories.insert_material()
    note_id = await factories.insert_note(material_id=material_id)
    deleted = await factories.insert_note(material_id=material_id)
    await notes_db.delete_note(note_id=deleted)

    notes = await update_notes_format.get_all_notes()

    assert [note.note_id for note in notes] == [note_id]


async def test_main_rewrites_the_content_of_every_live_note():
    material_id = await factories.insert_material()
    target = await factories.insert_note(material_id=material_id, title="Target")
    linked = await factories.insert_note(
        material_id=material_id,
        link_id=target,
        title="Linked",
        content=f"Первая строка<br/>вторая #тег #tag [[{target}]]",
        chapter="Глава 3",
        page=12,
        tags=["тег", "tag"],
    )
    deleted = await factories.insert_note(material_id=material_id, content="Deleted #tag")
    await notes_db.delete_note(note_id=deleted)
    before = await factories.fetch_row(models.Notes, linked)

    await update_notes_format.main()

    after = await factories.fetch_row(models.Notes, linked)
    assert after["content"] == "Первая строка\nвторая."
    assert sorted(after.pop("tags")) == sorted(before.pop("tags"))
    assert {**after, "content": None} == {**before, "content": None}
    assert (await factories.fetch_row(models.Notes, target))["content"] == "Note content."
    assert (await factories.fetch_row(models.Notes, deleted))["content"] == "Deleted #tag"


async def test_main_on_an_empty_database_does_nothing():
    await update_notes_format.main()

    assert await factories.count_rows(models.Notes) == 0
