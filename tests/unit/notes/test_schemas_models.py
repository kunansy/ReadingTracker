import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from tracker.models.models import MAX_CHAPTER_LENGTH
from tracker.notes import schemas


MATERIAL_ID = UUID(int=1)
LINK_ID = UUID(int=2)


def _form(**fields) -> schemas.Note:
    return schemas.Note(**({"material_id": MATERIAL_ID, "content": "Content"} | fields))


def _add(**fields) -> schemas.AddNoteRequest:
    return schemas.AddNoteRequest(
        **({"material_id": MATERIAL_ID, "content": "Content"} | fields),
    )


def _update(**fields) -> schemas.UpdateNoteRequest:
    values = {
        "material_id": MATERIAL_ID,
        "link_id": None,
        "title": None,
        "content": "Content",
    }
    return schemas.UpdateNoteRequest(**(values | fields))


class TestNoteForm:
    def test_only_required_fields_get_defaults(self):
        note = _form()

        assert note.model_dump() == {
            "material_id": MATERIAL_ID,
            "title": None,
            "content": "Content",
            "tags": None,
            "link_id": None,
            "chapter": "",
            "page": 0,
        }

    @pytest.mark.parametrize(
        ("tags", "expected"),
        [
            ("", None),
            ([], None),
            (None, None),
            ("tag", ["tag"]),
            ("b a", ["a", "b"]),
            ("#b #a", ["a", "b"]),
            ("##a", ["a"]),
            ("B A", ["a", "b"]),
            ("a a", ["a"]),
            ("  a \n b\t", ["a", "b"]),
            ("тег #Арбуз", ["арбуз", "тег"]),
            (["#B a"], ["a", "b"]),
            (["one"], ["one"]),
            ("#", []),
        ],
        ids=[
            "empty-string",
            "empty-list",
            "none",
            "single",
            "sorted",
            "hash-prefixes",
            "double-hash",
            "upper-case",
            "duplicates",
            "any-whitespace",
            "cyrillic",
            "one-element-list",
            "one-element-list-single-tag",
            "only-hash",
        ],
    )
    def test_tags_are_normalized(self, tags, expected):
        assert _form(tags=tags).tags == expected

    @pytest.mark.parametrize("tags", ["a-b", "ok bad!", ["a.b"], "a,b"])
    def test_invalid_tag_is_rejected(self, tags):
        with pytest.raises(ValidationError, match="Invalid tags"):
            _form(tags=tags)

    def test_multi_element_tags_list_is_accepted(self):
        assert _form(tags=["b", "#A"]).tags == ["a", "b"]

    @pytest.mark.parametrize(
        "tags", [[1], ["a", None], 5], ids=["int", "none-in-list", "int-value"]
    )
    def test_non_string_tag_is_a_validation_error(self, tags):
        with pytest.raises(ValidationError, match="Invalid tags"):
            _form(tags=tags)

    def test_validation_does_not_change_the_given_data(self):
        data = {
            "material_id": str(MATERIAL_ID),
            "content": "c",
            "tags": "#B a",
            "page": "3",
        }
        original = dict(data)

        schemas.Note.model_validate(data)

        assert data == original

    @pytest.mark.parametrize(
        ("page", "expected"),
        [("", 0), ("0", 0), (0, 0), (None, 0), ("12", 12), (12, 12), (" 7 ", 7)],
        ids=["empty", "zero-string", "zero", "none", "number-string", "int", "padded"],
    )
    def test_page_is_converted_to_int(self, page, expected):
        assert _form(page=page).page == expected

    @pytest.mark.parametrize(
        ("page", "message"),
        [
            ("garbage", "invalid literal for int"),
            ("1.5", "invalid literal for int"),
            ("-1", "greater than or equal to 0"),
            (-1, "greater than or equal to 0"),
        ],
        ids=["garbage", "float-string", "negative-string", "negative"],
    )
    def test_invalid_page_is_rejected(self, page, message):
        with pytest.raises(ValidationError, match=message):
            _form(page=page)

    def test_float_page_is_truncated_current_behaviour(self):
        assert _form(page=1.9).page == 1

    @pytest.mark.parametrize("data", [[1], "text", None, 5], ids=repr)
    def test_non_dict_input_is_a_validation_error(self, data):
        with pytest.raises(ValidationError):
            schemas.Note.model_validate(data)

    @pytest.mark.parametrize(
        ("field", "value", "expected"),
        [
            ("title", "", None),
            ("title", None, None),
            ("title", " Title ", "Title"),
            ("link_id", "", None),
            ("link_id", None, None),
            ("link_id", str(LINK_ID), LINK_ID),
        ],
    )
    def test_empty_form_values_become_none(self, field, value, expected):
        assert getattr(_form(**{field: value}), field) == expected

    def test_invalid_link_id_is_rejected(self):
        with pytest.raises(ValidationError, match="link_id"):
            _form(link_id="not-a-uuid")

    def test_content_is_formatted_and_double_spaces_removed(self):
        note = _form(content='  he   said "x^2  ->  \\inf"  --  ok  ')

        assert note.content == "He said «x<sup>2</sup> → ∞» — ok"

    def test_unbalanced_quotes_are_rejected(self):
        with pytest.raises(ValidationError, match="Quotes are not balanced"):
            _form(content='a "b')

    def test_content_is_required(self):
        with pytest.raises(ValidationError, match="content"):
            schemas.Note(material_id=MATERIAL_ID)

    def test_empty_content_is_accepted_current_behaviour(self):
        assert _form(content="   ").content == ""

    def test_extra_field_is_forbidden(self):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            _form(unknown=1)

    def test_chapter_at_the_limit_is_accepted(self):
        chapter = "1" * MAX_CHAPTER_LENGTH

        assert _form(chapter=chapter).chapter == chapter

    def test_chapter_over_the_limit_is_rejected(self):
        with pytest.raises(ValidationError, match="chapter"):
            _form(chapter="1" * (MAX_CHAPTER_LENGTH + 1))


class TestAddNoteRequest:
    def test_defaults(self):
        assert _add().model_dump() == {
            "material_id": MATERIAL_ID,
            "title": None,
            "content": "Content",
            "tags": [],
            "link_id": None,
            "chapter": "",
            "page": 0,
        }

    @pytest.mark.parametrize(
        ("tags", "expected"),
        [
            ([], []),
            (["b", "a"], ["a", "b"]),
            (["B", "a"], ["a", "b"]),
            ([" b ", "a"], ["a", "b"]),
            (["тег", "Арбуз"], ["арбуз", "тег"]),
            (["a_1", "10", "2"], ["10", "2", "a_1"]),
        ],
        ids=["empty", "sorted", "lowercased", "stripped", "cyrillic", "lexicographic"],
    )
    def test_tags_are_lowercased_stripped_and_sorted(self, tags, expected):
        assert _add(tags=tags).tags == expected

    def test_duplicate_tags_are_kept_current_behaviour(self):
        assert _add(tags=["a", "A"]).tags == ["a", "a"]

    @pytest.mark.parametrize(
        "tags",
        [["a b"], ["a-b"], ["#a"], [""], ["ok", "not ok"], "a", [1]],
        ids=["space", "hyphen", "hash", "empty", "second-invalid", "not-a-list", "int"],
    )
    def test_invalid_tags_are_rejected(self, tags):
        with pytest.raises(ValidationError, match="tags"):
            _add(tags=tags)

    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            ('note "quoted"', "Note «quoted»"),
            ("a -- b", "A — b"),
            ("a -> b <- c <-> d", "A → b ← c ↔ d"),
            ("x^2 y", "X<sup>2</sup> y"),
            ("to \\inf and", "To ∞ and"),
            ("a  b   c", "A b c"),
            ("  padded  ", "Padded"),
            ("line\n\nbreak", "Line\n\nbreak"),
            ("привет", "Привет"),
            ("", ""),
        ],
        ids=[
            "quotes",
            "dash",
            "arrows",
            "up-index",
            "infinity",
            "double-spaces",
            "stripped",
            "new-lines-kept",
            "cyrillic",
            "empty",
        ],
    )
    def test_content_is_formatted(self, content, expected):
        assert _add(content=content).content == expected

    def test_unbalanced_quotes_are_rejected(self):
        with pytest.raises(ValidationError, match="Quotes are not balanced"):
            _add(content='"a')

    @pytest.mark.parametrize("page", [-1, "x", 1.5])
    def test_invalid_page_is_rejected(self, page):
        with pytest.raises(ValidationError, match="page"):
            _add(page=page)

    @pytest.mark.parametrize("field", ["material_id", "link_id"])
    def test_invalid_uuid_is_rejected(self, field):
        with pytest.raises(ValidationError, match=field):
            _add(**{field: "not-a-uuid"})

    def test_chapter_at_the_limit_is_accepted(self):
        chapter = "1" * MAX_CHAPTER_LENGTH

        assert _add(chapter=chapter).chapter == chapter

    def test_chapter_over_the_limit_is_rejected(self):
        with pytest.raises(ValidationError, match="chapter"):
            _add(chapter="1" * (MAX_CHAPTER_LENGTH + 1))


class TestUpdateNoteRequest:
    def test_defaults(self):
        assert _update().model_dump() == {
            "material_id": MATERIAL_ID,
            "link_id": None,
            "title": None,
            "content": "Content",
            "tags": [],
            "chapter": "0",
            "page": 0,
        }

    @pytest.mark.parametrize("field", ["material_id", "link_id", "title", "content"])
    def test_field_without_default_is_required(self, field):
        values = {
            "material_id": MATERIAL_ID,
            "link_id": None,
            "title": None,
            "content": "Content",
        }
        del values[field]

        with pytest.raises(ValidationError, match=field):
            schemas.UpdateNoteRequest(**values)

    def test_content_is_formatted_like_a_new_note(self):
        content = 'he   said "x^2 -> \\inf" -- ok'

        assert _update(content=content).content == _add(content=content).content
        assert _update(content=content).content == "He said «x<sup>2</sup> → ∞» — ok"

    def test_unbalanced_quotes_are_rejected(self):
        with pytest.raises(ValidationError, match="Quotes are not balanced"):
            _update(content='a "b')

    def test_tags_are_lowercased_and_sorted(self):
        assert _update(tags=["b", " A "]).tags == ["a", "b"]

    def test_invalid_tag_is_rejected(self):
        with pytest.raises(ValidationError, match="tags"):
            _update(tags=["a b"])

    def test_negative_page_is_rejected(self):
        with pytest.raises(ValidationError, match="page"):
            _update(page=-1)

    def test_chapter_at_the_limit_is_accepted(self):
        chapter = "1" * MAX_CHAPTER_LENGTH

        assert _update(chapter=chapter).chapter == chapter

    def test_chapter_over_the_limit_is_rejected(self):
        with pytest.raises(ValidationError, match="chapter"):
            _update(chapter="1" * (MAX_CHAPTER_LENGTH + 1))


class TestSearchParams:
    def test_defaults(self):
        params = schemas.SearchParams()

        assert params.model_dump() == {
            "material_id": None,
            "query": None,
            "tags_query": None,
        }
        assert params.requested_tags() == set()

    @pytest.mark.parametrize(
        ("tags_query", "expected"),
        [
            (None, set()),
            ("", set()),
            ("   ", set()),
            ("a", {"a"}),
            ("a b", {"a", "b"}),
            ("a  b \n c\t", {"a", "b", "c"}),
            ("a a", {"a"}),
            ("#a B", {"#a", "B"}),
            ("тег", {"тег"}),
        ],
        ids=[
            "none",
            "empty",
            "blank",
            "single",
            "two",
            "any-whitespace",
            "duplicates",
            "kept-verbatim",
            "cyrillic",
        ],
    )
    def test_requested_tags(self, tags_query, expected):
        params = schemas.SearchParams(tags_query=tags_query)

        assert params.requested_tags() == expected

    @pytest.mark.parametrize("field", ["query", "tags_query"])
    def test_query_at_the_limit_is_accepted(self, field):
        value = "a" * schemas.MAX_SEARCH_QUERY_LENGTH

        assert getattr(schemas.SearchParams(**{field: value}), field) == value

    @pytest.mark.parametrize("field", ["query", "tags_query"])
    def test_query_over_the_limit_is_rejected(self, field):
        with pytest.raises(ValidationError, match="at most 512 characters"):
            schemas.SearchParams(**{field: "a" * 513})

    def test_limit_is_512(self):
        assert schemas.MAX_SEARCH_QUERY_LENGTH == 512

    def test_invalid_material_id_is_rejected(self):
        with pytest.raises(ValidationError, match="material_id"):
            schemas.SearchParams(material_id="x")


class TestNoteJson:
    def _note(self, **fields) -> schemas.NoteJson:
        values = {
            "note_id": UUID(int=3),
            "link_id": None,
            "material_id": MATERIAL_ID,
            "title": None,
            "content": "Content",
            "added_at": datetime.datetime(2024, 1, 2, 3, 4, 5, 678),  # noqa: DTZ001
            "chapter": "1",
            "page": 2,
            "tags": {"b", "a"},
            "is_deleted": False,
            "note_number": 7,
            "links_count": None,
        }
        return schemas.NoteJson(**(values | fields))

    def test_added_at_is_serialized_without_microseconds(self):
        assert self._note().model_dump()["added_at"] == "2024-01-02 03:04:05"

    def test_json_dump_keeps_native_types(self):
        dumped = self._note(links_count=3, link_id=LINK_ID).model_dump(mode="json")

        assert sorted(dumped.pop("tags")) == ["a", "b"]
        assert dumped == {
            "note_id": str(UUID(int=3)),
            "link_id": str(LINK_ID),
            "material_id": str(MATERIAL_ID),
            "title": None,
            "content": "Content",
            "added_at": "2024-01-02 03:04:05",
            "chapter": "1",
            "page": 2,
            "is_deleted": False,
            "note_number": 7,
            "links_count": 3,
        }

    def test_get_note_response_wraps_note(self):
        note = self._note()

        assert schemas.GetNoteResponse(note=note).note == note


class TestAutocompletionResponse:
    @pytest.mark.parametrize(
        ("variants", "expected"),
        [
            ([], []),
            (["plain"], ["plain"]),
            (["a<br/>b"], ["ab"]),
            (["a<br>b"], ["ab"]),
            (["a\nb\r\nc"], ["abc"]),
            (["<br/><br>\n\r"], [""]),
            (["a<br/>", "b\n"], ["a", "b"]),
            (["a<BR>b", "a<br />b"], ["a<BR>b", "a<br />b"]),
        ],
        ids=[
            "empty",
            "plain",
            "self-closed-br",
            "br",
            "new-lines",
            "only-breaks",
            "every-item",
            "other-spellings-kept",
        ],
    )
    def test_line_breaks_are_removed(self, variants, expected):
        response = schemas.AutocompletionResponse(autocompletions=variants)

        assert response.autocompletions == expected


def test_get_note_links_item_info_defaults_to_empty_string():
    assert schemas.GetNoteLinksItem(note_id=UUID(int=1)).info == ""
