import datetime
from uuid import UUID

import pytest
from pydantic import TypeAdapter, ValidationError

from tracker.common import schemas
from tracker.common.schemas import CustomBaseModel, MinMax, Tags, TagsQuery


LOG_ID = UUID("018e9dbe-1d3d-7a5a-b437-9bfa65171b42")
MATERIAL_ID = UUID("1c2fc59d-5313-4615-9290-e8668abe2fc0")


class _Model(CustomBaseModel):
    title: str
    comment: str | None = None


def test_custom_base_model_forbids_extra_fields():
    with pytest.raises(ValidationError) as exc_info:
        _Model(title="t", unknown=1)

    assert [(e["type"], e["loc"]) for e in exc_info.value.errors()] == [
        ("extra_forbidden", ("unknown",)),
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  title  ", "title"),
        ("\n\tЗаголовок \r\n", "Заголовок"),
        ("in  ner", "in  ner"),
        ("   ", ""),
        ("", ""),
    ],
    ids=["spaces", "cyrillic-with-newlines", "inner-spaces-kept", "only-spaces", "empty"],
)
def test_custom_base_model_strips_whitespace_around_strings(raw, expected):
    assert _Model(title=raw).title == expected


def test_custom_base_model_strips_optional_strings():
    assert _Model(title="t", comment=" c ").comment == "c"


def test_custom_base_model_keeps_none():
    assert _Model(title="t").comment is None


def test_min_max_accepts_valid_values():
    result = MinMax(
        log_id=str(LOG_ID),
        material_id=MATERIAL_ID,
        material_title=" Title ",
        count=0,
        date="2024-02-29",
    )

    assert result.model_dump() == {
        "log_id": LOG_ID,
        "material_id": MATERIAL_ID,
        "material_title": "Title",
        "count": 0,
        "date": datetime.date(2024, 2, 29),
    }


def test_min_max_rejects_negative_count():
    with pytest.raises(ValidationError) as exc_info:
        MinMax(
            log_id=LOG_ID,
            material_id=MATERIAL_ID,
            material_title="t",
            count=-1,
            date=datetime.date(2024, 1, 1),
        )

    assert [e["loc"] for e in exc_info.value.errors()] == [("count",)]


def test_min_max_rejects_empty_ids():
    with pytest.raises(ValidationError) as exc_info:
        MinMax(
            log_id="",
            material_id="",
            material_title="t",
            count=1,
            date=datetime.date(2024, 1, 1),
        )

    assert sorted(e["loc"] for e in exc_info.value.errors()) == [
        ("log_id",),
        ("material_id",),
    ]


class _TagsModel(CustomBaseModel):
    tags: Tags = []
    tags_query: TagsQuery = None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", []),
        ("   ", []),
        ("b a", ["a", "b"]),
        ("#B  a\tb", ["a", "b"]),
        ("Тег tag", ["tag", "тег"]),
        ("a\nb", ["a", "b"]),
        ("_a_ #_b", ["a", "b"]),
    ],
    ids=["empty", "blank", "sorted", "hash-case-dedupe", "cyrillic", "newline", "edge-underscores"],
)
def test_normalize_tags(raw, expected):
    assert schemas.normalize_tags(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["a-b", "a,b", "a.b", "c++", "a#b", "_", "a" * (schemas.MAX_TAG_LENGTH + 1)],
    ids=["hyphen", "comma", "dot", "plus", "inner-hash", "only-underscore", "too-long"],
)
def test_normalize_tags_rejects_invalid_tags(raw):
    with pytest.raises(ValueError, match="^Invalid tags$"):
        schemas.normalize_tags(raw)


def test_tags_are_stripped_lowercased_deduplicated_and_sorted():
    assert _TagsModel(tags=[" B", "a", "b "]).tags == ["a", "b"]


def test_tags_drop_a_leading_hash_and_edge_underscores():
    assert _TagsModel(tags=["#a", "_b_", "#_c"]).tags == ["a", "b", "c"]


@pytest.mark.parametrize("tag", ["a-b", "", "a b"], ids=["hyphen", "empty", "space"])
def test_tags_reject_a_non_word_tag(tag):
    with pytest.raises(ValidationError, match="tags.0"):
        _TagsModel(tags=[tag])


@pytest.mark.parametrize(
    ("tags_query", "expected"),
    [(None, None), ("", None), ("  ", None), (" #B a b", "a b")],
    ids=["none", "empty", "blank", "normalized"],
)
def test_tags_query_is_normalized(tags_query, expected):
    assert _TagsModel(tags_query=tags_query).tags_query == expected


def test_tags_query_rejects_a_non_word_tag():
    with pytest.raises(ValidationError, match="Invalid tags"):
        _TagsModel(tags_query="a-b")


def test_tags_query_rejects_a_query_over_the_limit():
    with pytest.raises(ValidationError, match="at most 512 characters"):
        _TagsModel(tags_query="a" * (schemas.MAX_SEARCH_QUERY_LENGTH + 1))



_TAG = TypeAdapter(schemas.Tag)


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("a", "a"),
        ("a_b", "a_b"),
        ("tag1", "tag1"),
        ("1", "1"),
        ("_a_", "a"),
        ("#a", "a"),
        ("Тег", "тег"),
        ("ŞŇ", "şň"),
        ("a\n", "a"),
        (" A ", "a"),
    ],
    ids=["letter", "underscore", "alnum", "digit", "edge-underscores", "leading-hash",
         "cyrillic", "latin-ext", "trailing-newline", "padded"],
)
def test_tag_accepts_unicode_letters_digits_and_underscore(tag, expected):
    assert _TAG.validate_python(tag) == expected


@pytest.mark.parametrize(
    "tag",
    ["", "_", "a-b", "a b", "a#b", "a.b", "a,b", "c++", "İ"],
    ids=[
        "empty",
        "only-underscore",
        "hyphen",
        "space",
        "inner-hash",
        "dot",
        "comma",
        "plus",
        "lowercases-to-a-combining-mark",
    ],
)
def test_tag_rejects_other_characters(tag):
    with pytest.raises(ValidationError, match="String should match pattern"):
        _TAG.validate_python(tag)


def test_tag_accepts_the_maximum_length():
    tag = "a" * schemas.MAX_TAG_LENGTH

    assert _TAG.validate_python(tag) == tag


def test_tag_rejects_a_tag_over_the_maximum_length():
    with pytest.raises(ValidationError, match="at most 128 characters"):
        _TAG.validate_python("a" * (schemas.MAX_TAG_LENGTH + 1))


def test_tags_accept_the_maximum_count():
    tags = [f"t{i:02}" for i in range(schemas.MAX_TAGS)]

    assert _TagsModel(tags=tags).tags == tags


def test_tags_reject_a_list_over_the_maximum_count():
    with pytest.raises(ValidationError, match="at most 32 tags"):
        _TagsModel(tags=[f"t{i:02}" for i in range(schemas.MAX_TAGS + 1)])


def test_tags_count_the_limit_after_deduplication():
    tags = ["a", "A", " a"] * 11

    assert _TagsModel(tags=tags).tags == ["a"]


def test_tag_limits_are_published_in_the_json_schema():
    defs = _TagsModel.model_json_schema()["$defs"]

    assert defs["Tag"] == {"maxLength": 128, "pattern": "^[\\p{L}\\p{N}_]+$", "type": "string"}
    assert defs["Tags"]["maxItems"] == 32
    assert defs["Tags"]["items"] == {"$ref": "#/$defs/Tag"}


@pytest.mark.parametrize(
    ("tags_query", "expected"),
    [(None, set()), ("b a", {"a", "b"}), ("#B a", {"a", "b"})],
    ids=["none", "plain", "normalized"],
)
def test_requested_tags_splits_the_normalized_query(tags_query, expected):
    assert schemas.TagsSearchParams(tags_query=tags_query).requested_tags() == expected
