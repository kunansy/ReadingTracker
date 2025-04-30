import datetime
import re
from typing import Annotated, Any
from uuid import UUID

from pydantic import (
    BeforeValidator,
    conint,
    field_serializer,
    field_validator,
    model_validator,
)

from tracker.common import settings
from tracker.common.schemas import CustomBaseModel, skip_empty_value


PUNCTUATION_MAPPING = {
    "--": "—",
    "–": "—",  # noqa: RUF001
    "<->": "↔",
    "->": "→",
    "<-": "←",
}
UP_INDEX_PATTERN = re.compile(r"(\S)\^(\S+)(\s)")

_TAG_PATTERN = r"(\w+)"
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


class Note(CustomBaseModel):
    material_id: UUID
    title: str | None = None
    content: str
    tags: list[str] | None = None
    link_id: Annotated[UUID | None, BeforeValidator(skip_empty_value)] = None
    chapter: str = ""
    page: conint(ge=0) = 0

    @field_validator("content")
    def format_content(cls, content: str) -> str:
        for formatter in NOTES_FORMATTERS:
            content = formatter(content)
        return content

    @field_validator("content")
    def fix_double_spaces(cls, content: str) -> str:
        return " ".join(content.split(" "))

    @model_validator(mode="before")
    @classmethod
    def validate_tags(cls, data: Any) -> Any:
        if tags := data.pop("tags", None):
            if isinstance(tags, list) and len(tags) == 1:
                tags = tags[0]
            # fmt: off
            tags = {
                tag.strip()
                for tag in tags.lower().replace("#", "").split()
                if tag.strip()
            }
            # fmt: on

            if any(not TAG_PATTERN.match(tag) for tag in tags):
                raise ValueError("Invalid tags")

            data["tags"] = sorted(tags)
        return data


class UpdateNote(Note):
    note_id: UUID

    def get_material_id(self) -> str:
        return str(self.material_id)


class SearchParams(CustomBaseModel):
    material_id: UUID | str | None = None
    query: str | None = None
    tags_query: str | None = None

    def requested_tags(self) -> set[str]:
        if not (tags_query := self.tags_query):
            return set()

        return {tag.strip() for tag in tags_query.split() if tag.strip()}


class IsNoteDeletedResponse(CustomBaseModel):
    note_id: UUID
    is_deleted: bool


class GetNoteJsonResponse(CustomBaseModel):
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


class GetMaterialNotes(CustomBaseModel):
    notes: list[GetNoteJsonResponse]
    material_id: UUID
