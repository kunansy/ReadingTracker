import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from tests.unit.notes.conftest import MATERIAL_ID, build_note, note_id
from tracker.common import settings
from tracker.notes import db


def _tag_link(tag: str) -> str:
    return (
        f'<a href={settings.TRACKER_URL}/notes/?tags_query={tag} target="_blank">#{tag}</a>'
    )


def test_tracker_url_is_pinned():
    assert settings.TRACKER_URL == "http://tracker.test"


class TestLoadTags:
    @pytest.mark.parametrize(
        ("tags", "expected"),
        [
            ('["a", "b"]', {"a", "b"}),
            ("[]", set()),
            ('["a", "a"]', {"a"}),
            ('["тег"]', {"тег"}),
            (["b", "a", "a"], {"a", "b"}),
            ([], set()),
            ({"a"}, {"a"}),
            (("a",), {"a"}),
        ],
        ids=[
            "json-string",
            "empty-json-array",
            "json-duplicates",
            "json-cyrillic",
            "list",
            "empty-list",
            "set",
            "tuple",
        ],
    )
    def test_tags_are_loaded_into_a_set(self, tags, expected):
        assert build_note(1, tags=tags).tags == expected

    @pytest.mark.parametrize("tags", ["not json", "", "{"])
    def test_invalid_json_string_is_rejected(self, tags):
        with pytest.raises(ValidationError, match="tags"):
            build_note(1, tags=tags)

    def test_json_null_is_loaded_as_no_tags(self):
        assert build_note(1, tags="null").tags == set()

    def test_null_tags_column_is_loaded_as_no_tags(self):
        assert build_note(1, tags=None).tags == set()


class TestSerialization:
    def test_added_at_is_serialized_with_settings_format(self):
        note = build_note(1, added_at=datetime.datetime(2024, 12, 31, 23, 59, 59, 999))  # noqa: DTZ001

        assert note.model_dump()["added_at"] == "2024-12-31 23:59:59"

    def test_json_dump_keeps_native_types(self):
        note = build_note(1, link=2, tags={"b", "a"}, title="Title", links_count=4)

        dumped = note.model_dump(mode="json")

        assert sorted(dumped.pop("tags")) == ["a", "b"]
        assert dumped == {
            "note_id": str(note_id(1)),
            "link_id": str(note_id(2)),
            "material_id": str(MATERIAL_ID),
            "title": "Title",
            "content": "note 1",
            "added_at": "2024-01-02 03:04:05",
            "chapter": "1",
            "page": 1,
            "is_deleted": False,
            "note_number": 1,
            "links_count": 4,
        }

    def test_optional_fields_default_to_none(self):
        note = db.Note(
            note_id=note_id(1),
            material_id=MATERIAL_ID,
            content="c",
            added_at=datetime.datetime(2024, 1, 1),  # noqa: DTZ001
            chapter="",
            page=0,
            tags=[],
            is_deleted=True,
            note_number=1,
        )

        assert (note.link_id, note.title, note.links_count) == (None, None, None)

    def test_to_note_reads_row_attributes(self, mocker):
        row = mocker.Mock(
            spec_set=list(db.Note.model_fields),
            note_id=note_id(5),
            link_id=None,
            material_id=MATERIAL_ID,
            title=None,
            content="from row",
            added_at=datetime.datetime(2024, 1, 1),  # noqa: DTZ001
            chapter="2",
            page=3,
            tags='["x"]',
            is_deleted=False,
            note_number=9,
            links_count=0,
        )

        note = db._to_note(row)

        assert note == build_note(
            5,
            content="from row",
            added_at=datetime.datetime(2024, 1, 1),  # noqa: DTZ001
            chapter="2",
            page=3,
            tags={"x"},
            note_number=9,
            links_count=0,
        )


class TestContent:
    def test_str_and_content_md_demark_html_entities(self):
        note = build_note(1, content="a &lt;b&gt; c")

        assert str(note) == "a <b> c"
        assert note.content_md == "a <b> c"

    def test_content_html_is_the_raw_content(self):
        assert build_note(1, content="a &lt;b&gt; c").content_html == "a &lt;b&gt; c"

    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            ("", "..."),
            ("short", "short..."),
            ("a" * 49, "a" * 49 + "..."),
            ("a" * 50, "a" * 50 + "..."),
            ("a" * 51, "a" * 50 + "..."),
            ("я" * 60, "я" * 50 + "..."),
        ],
        ids=["empty", "short", "49", "exactly-50", "51", "cyrillic"],
    )
    def test_short_content_keeps_first_50_characters(self, content, expected):
        assert build_note(1, content=content).short_content == expected

    def test_short_content_is_cut_after_demarking(self):
        note = build_note(1, content="&lt;" * 60)

        assert note.short_content == "<" * 50 + "..."

    def test_info(self):
        note = build_note(7, content="a &gt; b")

        assert note.info == (
            f"ID: {note_id(7)}\nNumber: 7\nMaterial ID: {MATERIAL_ID}\n\na > b"
        )

    @pytest.mark.parametrize(
        ("chapter", "expected"),
        [("12", 12), ("Chapter 3", 3), ("", 0), ("intro", 0)],
    )
    def test_chapter_int(self, chapter, expected):
        assert build_note(1, chapter=chapter).chapter_int == expected

    @pytest.mark.parametrize(
        ("content", "from_", "to", "expected"),
        [
            ("find me", "me", "<b>me</b>", "find <b>me</b>"),
            ("me and me", "me", "X", "X and X"),
            ("nothing", "absent", "X", "nothing"),
            ("Case", "case", "X", "Case"),
        ],
        ids=["once", "every-occurrence", "absent", "case-sensitive"],
    )
    def test_highlight_replaces_in_place(self, content, from_, to, expected):
        note = build_note(1, content=content)

        note.highlight(from_, to)

        assert note.content == expected


class TestMarkTagsWithRef:
    @pytest.mark.parametrize(
        ("text", "tags", "expected"),
        [
            ("#a_tag", {"a_tag"}, _tag_link("a_tag")),
            (
                "any text #with or #without a tag",
                set(),
                "any text #with or #without a tag",
            ),
            (
                "#a_tag #another-tag #tag",
                {"a_tag", "another-tag", "tag"},
                f"{_tag_link('a_tag')} {_tag_link('another-tag')} {_tag_link('tag')}",
            ),
            (
                "text with tags, some content and #some #tags",
                {"some", "tags", "tag"},
                "text with tags, some content and "
                f"{_tag_link('some')} {_tag_link('tags')}",
            ),
            (
                "a link https://blog.burntsushi.net/ripgrep#single-file-benchmarks "
                "#and #tags",
                {"and", "tags", "single"},
                "a link https://blog.burntsushi.net/ripgrep#single-file-benchmarks "
                f"{_tag_link('and')} {_tag_link('tags')}",
            ),
            ("text # only", {"text", "only"}, "text # only"),
            ("#тег в конце", {"тег"}, f"{_tag_link('тег')} в конце"),
            ("#tag #tag", {"tag"}, f"{_tag_link('tag')} {_tag_link('tag')}"),
            ("#Tag", {"tag"}, "#Tag"),
            ("", {"tag"}, ""),
        ],
        ids=[
            "single",
            "no-tags-requested",
            "several",
            "longer-tag-wins-over-its-prefix",
            "url-fragment-is-not-a-tag",
            "lonely-hash",
            "cyrillic",
            "repeated",
            "case-sensitive",
            "empty-text",
        ],
    )
    def test_requested_tags_become_links(self, text, tags, expected):
        assert db.Note._mark_tags_with_ref(text, tags) == expected

    def test_tag_is_not_regex_escaped_current_behaviour(self):
        marked = db.Note._mark_tags_with_ref("#a.c #abc", {"a.c"})

        assert marked == f"{_tag_link('a.c')} {_tag_link('a.c')}"


class TestHtmlProperties:
    def test_link_html_points_to_note_page(self):
        note = build_note(1, link=2)

        assert note.link_html == (
            f'<a class="link-ref" href=http://tracker.test/notes/{note_id(2)} '
            f'target="_blank">[[{note_id(2)}]]</a>'
        )

    def test_link_html_is_empty_without_link(self):
        assert build_note(1).link_html == ""

    @pytest.mark.parametrize(
        ("tags", "expected"),
        [
            (set(), ""),
            ({"one"}, "#one"),
            ({"b", "a", "c"}, "#a #b #c"),
            ({"тег", "abc"}, "#abc #тег"),
        ],
        ids=["empty", "single", "sorted", "cyrillic-after-latin"],
    )
    def test_tags_str(self, tags, expected):
        assert build_note(1, tags=tags).tags_str == expected

    def test_tags_html_links_every_tag(self):
        note = build_note(1, tags={"tags", "tag"})

        assert note.tags_html == f"{_tag_link('tag')} {_tag_link('tags')}"

    def test_tags_html_is_empty_without_tags(self):
        assert build_note(1).tags_html == ""


def test_note_rejects_unknown_field():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        build_note(1, unknown=1)


def test_note_ids_are_uuids():
    assert isinstance(build_note(1).note_id, UUID)
