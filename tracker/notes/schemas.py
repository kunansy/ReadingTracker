import re
from typing import Any, TypedDict
from uuid import UUID

from fastapi import Form
from pydantic import conint, constr, field_validator, model_validator

from tracker.common.schemas import CustomBaseModel


PUNCTUATION_MAPPING = {
    "--": "—",
    "–": "—",  # noqa: RUF001
    "<->": "↔",
    "->": "→",
    "<-": "←",
}
# this is a legacy, since the last time Markdown syntax is used
BOLD_MARKER = "font-weight-bold"
ITALIC_MARKER = "font-italic"
CODE_MARKER = "font-code"

# save back compatibility with css style for now
DEMARK_BOLD_PATTERN = re.compile(f'<span class="?{BOLD_MARKER}"?>(.*?)</span>')
DEMARK_ITALIC_PATTERN = re.compile(f'<span class="?{ITALIC_MARKER}"?>(.*?)</span>')
DEMARK_CODE_PATTERN = re.compile(f'<span class="?{CODE_MARKER}"?>(.*?)</span>')

UP_INDEX_PATTERN = re.compile(r"(\S)\^(\S+)(\s)")

TAG_PATTERN = re.compile(r"(\w+)")
TAGS_PATTERN = re.compile(rf"\W#{TAG_PATTERN}\b")
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


def _demark_bold(string: str) -> str:
    return DEMARK_BOLD_PATTERN.sub(r"**\1**", string)


def _demark_italic(string: str) -> str:
    return DEMARK_ITALIC_PATTERN.sub(r"*\1*", string)


def _demark_code(string: str) -> str:
    return DEMARK_CODE_PATTERN.sub(r"`\1`", string)


def _dereplace_lt(string: str) -> str:
    return re.sub(r"&lt;", "<", string)


def _dereplace_gt(string: str) -> str:
    return re.sub(r"&gt;", ">", string)


def dereplace_new_lines(string: str) -> str:
    return re.sub(r"<br/?>", "\n", string)


NOTES_FORMATTERS = (
    _replace_quotes,
    add_dot,
    _up_first_letter,
    _replace_punctuation,
    _replace_up_index,
    _replace_inf,
)

NOTES_DEMARKERS = (
    _demark_bold,
    _demark_italic,
    _demark_code,
    _dereplace_lt,
    _dereplace_gt,
    dereplace_new_lines,
)


def demark_note(string: str) -> str:
    """To show the note in update form."""
    for formatter in NOTES_DEMARKERS:
        string = formatter(string)
    return string


class Note(CustomBaseModel):
    material_id: UUID | None
    title: str | None = None
    content: constr(strip_whitespace=True)
    tags: list[str] | None = None
    link_id: UUID | None = None
    chapter: constr(strip_whitespace=True) = ""
    page: conint(ge=0) = 0

    def __init__(
        self,
        material_id: UUID = Form(None),
        title: str | None = Form(None),
        content: str = Form(...),
        tags: list[str] | None = Form(None),
        link_id: UUID | None = Form(None),
        chapter: str = Form(""),
        page: int = Form(0),
        **kwargs,
    ):
        super().__init__(
            material_id=material_id,
            title=title,
            content=content,
            tags=tags,
            link_id=link_id,
            chapter=chapter,
            page=page,
            **kwargs,
        )

    @field_validator("content")
    def validate_double_brackets_count(cls, content: str) -> str:
        assert content.count("[[") == content.count("]]")

        if "[[" in content and "]]" in content:
            assert LINK_PATTERN.search(content) is not None

        return content

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
        if tags := data.get("tags"):
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

    def __init__(
        self,
        material_id: UUID | None = Form(None),
        note_id: UUID = Form(...),
        title: str | None = Form(None),
        content: str = Form(...),
        tags: list[str] | None = Form(None),
        link_id: UUID | None = Form(None),
        chapter: str = Form(""),
        page: int = Form(0),
    ):
        super().__init__(
            material_id=material_id,
            note_id=note_id,
            title=title,
            content=content,
            tags=tags,
            link_id=link_id,
            chapter=chapter,
            page=page,
        )

    def get_material_id(self) -> str | None:
        if self.material_id in (UUID(int=0), None):
            return None
        return str(self.material_id)


class SearchParams(CustomBaseModel):
    material_id: UUID | str | None = None
    query: constr(strip_whitespace=True) | None = None
    tags_query: constr(strip_whitespace=True) | None = None

    def requested_tags(self) -> set[str]:
        if not (tags_query := self.tags_query):
            return set()

        return {tag.strip() for tag in tags_query.split() if tag.strip()}


class RecognitionResult(TypedDict):
    transcript: str
    confidence: float


class TranscriptTextResponse(CustomBaseModel):
    transcript: str
    confidence: float

    @field_validator("transcript")
    def capitalize_transcript(cls, transcript: str) -> str:
        return transcript.capitalize()

    @field_validator("confidence")
    def convert_to_percent(cls, value: float) -> float:
        return round(value * 100, 2)


class IsNoteDeletedResponse(CustomBaseModel):
    note_id: UUID
    is_deleted: bool


class GetNoteJsonResponse(CustomBaseModel):
    note_id: UUID
    link_id: UUID | None
    material_id: UUID
    title: str | None
    content: str
    added_at: str
    chapter: str
    page: int
    tags: set[str]
    is_deleted: bool
    note_number: int
    links_count: int | None
