import re
from typing import TypedDict
from uuid import UUID

from fastapi import Form
from pydantic import conint, constr, field_validator

from tracker.common.schemas import CustomBaseModel


PUNCTUATION_MAPPING = {
    "--": "—",
    "<->": "↔",
    "->": "→",
    "<-": "←",
}
BOLD_MARKER = "font-weight-bold"
ITALIC_MARKER = "font-italic"
CODE_MARKER = "font-code"

DEMARK_BOLD_PATTERN = re.compile(f'<span class="?{BOLD_MARKER}"?>(.*?)</span>')
DEMARK_ITALIC_PATTERN = re.compile(f'<span class="?{ITALIC_MARKER}"?>(.*?)</span>')
DEMARK_CODE_PATTERN = re.compile(f'<span class="?{CODE_MARKER}"?>(.*?)</span>')

TAGS_PATTERN = re.compile(r'#(\w+)\b')
LINK_PATTERN = re.compile(r'\[\[([0-9a-fA-F]{8}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{12})\]\]')


def _replace_quotes(string: str) -> str:
    count = string.count('"')
    assert count % 2 == 0, "Quotes are not balanced"

    for _ in range(count // 2):
        string = string.replace('"', "«", 1)
        string = string.replace('"', "»", 1)
    return string


def _add_dot(string: str) -> str:
    if not string or string.endswith(('.', '?', '!')):
        return string
    return f"{string}."


def _up_first_letter(string: str) -> str:
    if not string or string[0].isupper():
        return string
    return f"{string[0].upper()}{string[1:]}"


def _replace_punctuation(string: str) -> str:
    for src, dst in PUNCTUATION_MAPPING.items():
        string = string.replace(src, dst)
    return string


def _replace_new_lines(string: str) -> str:
    return string.replace("\n", "<br/>")


def _replace_lt(string: str) -> str:
    return string.replace(' < ', " &lt; ")


def _replace_gt(string: str) -> str:
    return string.replace(' > ', " &gt; ")


def _mark_bold(string: str) -> str:
    count = string.count('**')
    assert count % 2 == 0, "Bold markers are not balanced"

    for _ in range(count // 2):
        # don't add quotes around class names, because
        # quotes will be replaced by the quotes formatter
        string = string.replace("**", f"<span class={BOLD_MARKER}>", 1)
        string = string.replace("**", "</span>", 1)
    return string


def _mark_italic(string: str) -> str:
    count = string.count('__')
    assert count % 2 == 0, "Italic markers are not balanced"

    for _ in range(count // 2):
        string = string.replace("__", f"<span class={ITALIC_MARKER}>", 1)
        string = string.replace("__", "</span>", 1)
    return string


def _mark_code(string: str) -> str:
    count = string.count('`')
    assert count % 2 == 0, "Code markers are not balanced"

    for _ in range(count // 2):
        string = string.replace("`", f"<span class={CODE_MARKER}>", 1)
        string = string.replace("`", "</span>", 1)
    return string


def _demark_bold(string: str) -> str:
    return DEMARK_BOLD_PATTERN.sub(r'**\1**', string)


def _demark_italic(string: str) -> str:
    return DEMARK_ITALIC_PATTERN.sub(r'__\1__', string)


def _demark_code(string: str) -> str:
    return DEMARK_CODE_PATTERN.sub(r'`\1`', string)


def _dereplace_new_lines(string: str) -> str:
    return re.sub(r'<br/?>', '\n', string)


NOTES_FORMATTERS = (
    _replace_quotes,
    _add_dot,
    _up_first_letter,
    _replace_punctuation,
    _replace_lt,
    _replace_gt,
    _mark_bold,
    _mark_italic,
    _mark_code,
    _replace_new_lines,
)

NOTES_DEMARKERS = (
    _demark_bold,
    _demark_italic,
    _demark_code,
    _dereplace_new_lines,
)


def demark_note(string: str) -> str:
    """ to show the note in update form """
    for formatter in NOTES_DEMARKERS:
        string = formatter(string)
    return string


class Note(CustomBaseModel):
    material_id: UUID | None
    content: constr(strip_whitespace=True)
    chapter: conint(ge=0) = 0
    page: conint(ge=0) = 0

    def __init__(self,
                 material_id: UUID = Form(None),
                 content: str = Form(...),
                 chapter: int = Form(0),
                 page: int = Form(0),
                 **kwargs):
        super().__init__(
            material_id=material_id,
            content=content,
            chapter=chapter,
            page=page,
            **kwargs
        )

    @field_validator('content')
    def validate_double_brackets_count(cls,
                                       content: str) -> str:
        assert content.count('[[') == content.count(']]')

        return content

    @field_validator('content')
    def format_content(cls,
                       content: str) -> str:
        for formatter in NOTES_FORMATTERS:
            content = formatter(content)
        return content

    @property
    def link_id(self) -> UUID | None:
        if link := LINK_PATTERN.search(self.content):
            return UUID(link.group(1))

        return None

    @property
    def tags(self) -> list[str]:
        if tags := TAGS_PATTERN.findall(self.content):
            return [tag.strip().lower() for tag in tags]

        return []


class UpdateNote(Note):
    note_id: UUID

    def __init__(self,
                 material_id: UUID | None = Form(None),
                 note_id: UUID = Form(...),
                 content: str = Form(...),
                 chapter: int = Form(0),
                 page: int = Form(0)):
        super().__init__(
            material_id=material_id,
            note_id=note_id,
            content=content,
            chapter=chapter,
            page=page,
        )

    @property
    def material_id(self) -> str | None:
        if self.material_id == UUID(int=0):
            return None
        return str(self.material_id)


class SearchParams(CustomBaseModel):
    material_id: UUID | str | None = None
    query: constr(strip_whitespace=True) | None = None
    tags_query: constr(strip_whitespace=True) | None = None

    def requested_tags(self) -> set[str]:
        if not (tags_query := self.tags_query):
            return set()

        return set(
            tag.strip()
            for tag in tags_query.split()
            if tag.strip()
        )


class RecognitionResult(TypedDict):
    transcript: str
    confidence: float


class TranscriptTextResponse(CustomBaseModel):
    transcript: str
    confidence: float

    @field_validator('transcript')
    def capitalize_transcript(cls, transcript: str) -> str:
        return transcript.capitalize()

    @field_validator('confidence')
    def convert_to_percent(cls, value: float) -> float:
        return round(value * 100, 2)


class IsNoteDeletedResponse(CustomBaseModel):
    note_id: UUID
    is_deleted: bool


class GetNoteJsonResponse(CustomBaseModel):
    note_id: UUID
    link_id: UUID | None
    material_id: UUID
    content: str
    added_at: str
    chapter: int
    page: int
    tags: set[str]
    is_deleted: bool
    note_number: int
    links_count: int | None
