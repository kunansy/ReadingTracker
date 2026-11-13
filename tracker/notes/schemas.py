import datetime
import re
from typing import Annotated, Any, Final
from uuid import UUID

from pydantic import (
    BeforeValidator,
    Field,
    NonNegativeInt,
    conlist,
    constr,
    field_serializer,
    field_validator,
    model_validator,
)

from tracker.common import settings
from tracker.common.pagination import PageResponse
from tracker.common.schemas import CustomBaseModel, skip_empty_value
from tracker.models.enums import MaterialTypesEnum
from tracker.models.models import MAX_CHAPTER_LENGTH


MAX_SEARCH_QUERY_LENGTH: Final[int] = 512


PUNCTUATION_MAPPING = {
    "--": "—",
    "–": "—",  # noqa: RUF001
    "<->": "↔",
    "->": "→",
    "<-": "←",
}
UP_INDEX_PATTERN = re.compile(r"(\S)\^(\S+)(\s)")

# TODO: implement test
_TAG_PATTERN = r"^(\w+)$"
TAG_PATTERN = re.compile(_TAG_PATTERN)
LINK_PATTERN = re.compile(
    r"\[\[([0-9a-fA-F]{8}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{12})\]\]",
)


def _replace_quotes(string: str) -> str:
    count = string.count('"')
    assert count % 2 == 0, "Quotes are not balanced"

    for _ in range(count // 2):
        string = string.replace('"', "«", 1)
        string = string.replace('"', "»", 1)
    return string


def add_dot(string: str) -> str:
    if not string or string.endswith((".", "?", "!")):
        return string
    return f"{string}."


def _up_first_letter(string: str) -> str:
    if not string or string[0].isupper():
        return string
    return f"{string[0].upper()}{string[1:]}"


def _replace_punctuation(string: str) -> str:
    for src, dst in PUNCTUATION_MAPPING.items():
        string = string.replace(f" {src} ", f" {dst} ")
    return string


def _replace_inf(string: str) -> str:
    return string.replace("\\inf", "∞")


def _replace_up_index(string: str) -> str:
    return UP_INDEX_PATTERN.sub(r"\1<sup>\2</sup>\3", string)


def _dereplace_lt(string: str) -> str:
    return re.sub(r"&lt;", "<", string)


def _dereplace_gt(string: str) -> str:
    return re.sub(r"&gt;", ">", string)


NOTES_FORMATTERS = (
    _replace_quotes,
    _up_first_letter,
    _replace_punctuation,
    _replace_up_index,
    _replace_inf,
)

NOTES_DEMARKERS = (
    _dereplace_lt,
    _dereplace_gt,
)


def demark_note(string: str) -> str:
    """To show the note in update form."""
    for formatter in NOTES_DEMARKERS:
        string = formatter(string)
    return string


type Chapter = Annotated[str, Field(max_length=MAX_CHAPTER_LENGTH)]


def _normalize_form_tags(tags: object) -> list[str]:
    if isinstance(tags, list):
        if not all(isinstance(tag, str) for tag in tags):
            raise ValueError("Invalid tags")
        tags = " ".join(tags)
    if not isinstance(tags, str):
        # pydantic turns only ValueError into a validation error
        raise ValueError("Invalid tags")  # noqa: TRY004

    normalized = {tag for tag in tags.lower().replace("#", "").split() if tag}
    if any(not TAG_PATTERN.match(tag) for tag in normalized):
        raise ValueError("Invalid tags")
    return sorted(normalized)


class Note(CustomBaseModel):
    material_id: UUID
    title: Annotated[str | None, BeforeValidator(skip_empty_value)] = None
    content: str
    tags: list[str] | None = None
    link_id: Annotated[UUID | None, BeforeValidator(skip_empty_value)] = None
    chapter: Chapter = ""
    page: NonNegativeInt = 0

    @field_validator("content")
    def format_content(cls, content: str) -> str:
        for formatter in NOTES_FORMATTERS:
            content = formatter(content)
        return content

    @field_validator("content")
    def fix_double_spaces(cls, content: str) -> str:
        return " ".join(word for word in content.split(" ") if word)

    @model_validator(mode="before")
    @classmethod
    def validate_tags(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        tags = data.get("tags")
        rest = {key: value for key, value in data.items() if key != "tags"}
        if not tags:
            return rest
        return {**rest, "tags": _normalize_form_tags(tags)}

    @model_validator(mode="before")
    @classmethod
    def validate_page(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        page = data.get("page")
        rest = {key: value for key, value in data.items() if key != "page"}
        if not page:
            return rest
        return {**rest, "page": int(page)}


type Tags = conlist(constr(pattern=TAG_PATTERN, to_lower=True, strip_whitespace=True))


class _NoteBody(CustomBaseModel):
    """Formatting shared by the requests that write a note."""

    @field_validator("content", check_fields=False)
    def format_content(cls, content: str) -> str:
        for formatter in NOTES_FORMATTERS:
            content = formatter(content)
        return content

    @field_validator("content", check_fields=False)
    def fix_double_spaces(cls, content: str) -> str:
        return " ".join(word for word in content.split(" ") if word)

    @field_validator("tags", check_fields=False)
    def format_tags(cls, tags: list[str]) -> list[str]:
        return sorted(tags)


class AddNoteRequest(_NoteBody):
    material_id: UUID
    title: str | None = None
    content: str
    tags: Tags = Field(default_factory=list)
    link_id: UUID | None = None
    chapter: Chapter = ""
    page: NonNegativeInt = 0


class AddNoteResponse(CustomBaseModel):
    note_id: UUID


class UpdateNoteRequest(_NoteBody):
    material_id: UUID
    link_id: UUID | None
    title: str | None
    content: str
    tags: Tags = Field(default_factory=list)
    chapter: Chapter = "0"
    page: NonNegativeInt = 0


class SearchParams(CustomBaseModel):
    material_id: UUID | None = None
    query: Annotated[str | None, Field(max_length=MAX_SEARCH_QUERY_LENGTH)] = None
    tags_query: Annotated[str | None, Field(max_length=MAX_SEARCH_QUERY_LENGTH)] = None

    def requested_tags(self) -> set[str]:
        if not (tags_query := self.tags_query):
            return set()

        return {tag.strip() for tag in tags_query.split() if tag.strip()}


class NoteJson(CustomBaseModel):
    note_id: UUID
    link_id: UUID | None
    material_id: UUID
    title: str | None
    content: str
    added_at: datetime.datetime
    chapter: str
    page: int
    tags: set[str]
    is_deleted: bool
    note_number: int
    links_count: int | None

    @field_serializer("added_at")
    def serialize_added_at(self, added_at: datetime.datetime) -> str:
        return added_at.strftime(settings.DATETIME_FORMAT)


class GetNoteResponse(CustomBaseModel):
    note: NoteJson


class AutocompletionResponse(CustomBaseModel):
    autocompletions: list[str]

    @field_validator("autocompletions")
    def remove_new_lines(cls, autocompletions: list[str]) -> list[str]:
        return [
            variant.replace("<br/>", "")
            .replace("<br>", "")
            .replace("\n", "")
            .replace("\r", "")
            for variant in autocompletions
        ]


class NoteTagsResponse(CustomBaseModel):
    tags: list[str]


class GetNotesMetaResponse(CustomBaseModel):
    tags: list[str]
    titles: dict[UUID, str]


class GetNotesGraphResponse(CustomBaseModel):
    iframe_srcdoc: str
    titles: dict[UUID, str]
    material_id: UUID | None


class SearchNotesItem(CustomBaseModel):
    note_id: UUID
    material_id: UUID
    title: str | None
    content_html: str
    tags_html: str
    link_html: str
    chapter: str
    chapter_int: int
    page: int
    links_count: int | None
    is_deleted: bool


class SearchNotesResponse(PageResponse):
    notes: list[SearchNotesItem]
    titles: dict[UUID, str]
    material_types: dict[UUID, MaterialTypesEnum]
    material_notes: dict[UUID, int]
    chapters: dict[UUID, list[str]]
    query: str | None
    tags: list[str]
    tags_query: str | None
    page_size: int
    material_id: UUID | None


class ListPossibleLinksItem(CustomBaseModel):
    note_id: UUID
    title: str | None
    content: str
    tags: set[str]


class ListPossibleNoteLinksResponse(CustomBaseModel):
    items: list[ListPossibleLinksItem]


class GetNoteLinksItem(CustomBaseModel):
    note_id: UUID
    info: str = ""


class GetNoteLinksResponse(PageResponse):
    link_to: GetNoteLinksItem | None
    links_from: list[GetNoteLinksItem] | None
