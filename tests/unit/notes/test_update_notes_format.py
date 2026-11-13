import logging
from uuid import UUID

import pytest

from migrations import update_notes_format as migration
from tests.unit.notes.conftest import MATERIAL_ID, build_note, note_id
from tracker.common import settings
from tracker.notes import db as notes_db


LINK_ID = UUID("fde197da-0c98-451e-a3aa-eb86116ab964")


@pytest.mark.parametrize(
    ("text", "tags", "expected"),
    [
        ("text #tag", {"tag"}, "text "),
        ("#a text #b", {"a", "b"}, " text "),
        ("text #tag", set(), "text #tag"),
        ("text #tags", {"tag"}, "text #tags"),
        ("url#tag", {"tag"}, "url#tag"),
        ("", {"tag"}, ""),
    ],
    ids=["single", "several", "no-tags", "longer-word-kept", "inside-word-kept", "empty"],
)
def test_delete_tags(text, tags, expected):
    assert migration._delete_tags(text, tags) == expected


@pytest.mark.parametrize(
    ("text", "link_id", "expected"),
    [
        (f"text [[{LINK_ID}]]", LINK_ID, "text "),
        (f"text [[{LINK_ID}]]", str(LINK_ID), "text "),
        (f"[[{LINK_ID}]] and [[{LINK_ID}]]", LINK_ID, " and "),
        (f"text [[{LINK_ID}]]", None, f"text [[{LINK_ID}]]"),
        (f"text [[{LINK_ID}]]", "", f"text [[{LINK_ID}]]"),
        (f"text [[{LINK_ID}]]", UUID(int=1), f"text [[{LINK_ID}]]"),
    ],
    ids=["uuid", "string", "every-occurrence", "none", "empty", "another-link"],
)
def test_delete_link(text, link_id, expected):
    assert migration._delete_link(text, link_id) == expected


@pytest.mark.parametrize(
    ("string", "expected"),
    [
        ("a<br>b", "a\nb"),
        ("a<br/>b", "a\nb"),
        ("<br><br/>", "\n\n"),
        ("a<br />b", "a<br />b"),
        ("plain", "plain"),
    ],
)
def test_dereplace_new_lines(string, expected):
    assert migration._dereplace_new_lines(string) == expected


@pytest.mark.parametrize(
    ("string", "expected"),
    [("", ""), ("a", "a."), ("a.", "a."), ("a?", "a?"), ("a!", "a!")],
)
def test_add_dot(string, expected):
    assert migration.add_dot(string) == expected


@pytest.mark.parametrize(
    ("content", "tags", "link_id", "expected"),
    [
        ("text", set(), None, "text."),
        ("text.", set(), None, "text."),
        ("text?", set(), None, "text."),
        ("text!!!", set(), None, "text!!"),
        ("text . ", set(), None, "text."),
        ("text #tag", {"tag"}, None, "text."),
        (f"text<br/>#tag<br>[[{LINK_ID}]]", {"tag"}, LINK_ID, "text."),
        ("line<br>two", set(), None, "line\ntwo."),
        ("", set(), None, ""),
        ("?", set(), None, ""),
    ],
    ids=[
        "dot-added",
        "dot-kept",
        "question-becomes-dot",
        "only-one-ending-char-removed",
        "space-before-dot",
        "tag-removed",
        "tag-link-and-breaks-removed",
        "inner-break-kept",
        "empty",
        "only-punctuation",
    ],
)
def test_format_content_helper(content, tags, link_id, expected):
    assert migration._format_content(content, tags, link_id) == expected


def test_format_content_demarks_html_entities():
    note = build_note(1, content="a &lt; b &gt; c")

    assert migration.format_content(note) == "a < b > c."


def test_format_content_is_silent_when_every_hash_is_a_tag(caplog):
    note = build_note(1, content="text #a #b", tags={"a", "b"})

    with caplog.at_level(logging.WARNING, logger=settings.LOGGER_NAME):
        content = migration.format_content(note)

    assert content == "text."
    assert caplog.messages == []


def test_format_content_warns_when_hash_count_differs_from_tags(caplog):
    note = build_note(1, content="text #a # b", tags={"a"})

    with caplog.at_level(logging.WARNING, logger=settings.LOGGER_NAME):
        content = migration.format_content(note)

    assert content == "text  # b."
    assert caplog.messages == [
        "Might be an error when deleting tags: "
        f"note_id={note_id(1)}, tags={{'a'}}, content='text #a # b'",
        "Clean content: 'text  # b.'",
    ]


async def test_update_note_saves_formatted_content(mocker):
    update = mocker.patch.object(notes_db, "update_note", mocker.AsyncMock())
    note = build_note(1, link=2, title="Title", content="text #tag", tags={"tag"}, page=5)

    await migration.update_note(note)

    update.assert_awaited_once_with(
        note_id=note_id(1),
        material_id=MATERIAL_ID,
        link_id=note_id(2),
        title="Title",
        content="text.",
        page=5,
        chapter="1",
        tags=["tag"],
    )


async def test_main_updates_every_note(mocker):
    notes = [build_note(1), build_note(2)]
    get_notes = mocker.patch.object(
        notes_db,
        "get_notes",
        mocker.AsyncMock(return_value=notes),
    )
    update = mocker.patch.object(notes_db, "update_note", mocker.AsyncMock())

    await migration.main()

    get_notes.assert_awaited_once_with()
    assert [call.kwargs["note_id"] for call in update.await_args_list] == [
        note_id(1),
        note_id(2),
    ]


async def test_main_without_notes_updates_nothing(mocker):
    mocker.patch.object(notes_db, "get_notes", mocker.AsyncMock(return_value=[]))
    update = mocker.patch.object(notes_db, "update_note", mocker.AsyncMock())

    await migration.main()

    update.assert_not_awaited()
