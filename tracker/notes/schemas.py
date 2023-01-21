import re
from typing import Any
from uuid import UUID

from fastapi import Form
from pydantic import conint, constr, validator

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

TAGS_PATTERN = re.compile(r'#([\w-]+)\b')
LINK_PATTERN = re.compile(r'\[\[([0-9a-fA-F]{8}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{4}\b-[0-9a-fA-F]{12})\]\]')


def _replace_quotes(string: str) -> str:
    count = string.count('"')
    assert count % 2 == 0, "Quotes are not balanced"

    for _ in range(count // 2):
        string = string.replace('"', "«", 1)
        string = string.replace('"', "»", 1)
    return string


def _add_dot(string: str) -> str:
    if not string.endswith(('.', '?', '!')):
        return f"{string}."
    return string


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
    material_id: UUID
    content: constr(strip_whitespace=True)
    link_id: UUID | None = None
    chapter: conint(ge=0) = 0
    page: conint(ge=0) = 0
    tags: list[str]

    def __init__(self,
                 tags: list[str],
                 link_id: UUID | None = None,
                 material_id: UUID = Form(...),
                 content: str = Form(...),
                 chapter: int = Form(0),
                 page: int = Form(0),
                 **kwargs):
        super().__init__(
            material_id=material_id,
            link_id=link_id,
            content=content,
            chapter=chapter,
            page=page,
            tags=tags,
            **kwargs
        )

    @validator('content')
    def validate_double_brackets_count(cls,
                                       content: str) -> str:
        assert content.count('[[') == content.count(']]')

        return content

    @validator('content')
    def format_content(cls,
                       content: str) -> str:
        for formatter in NOTES_FORMATTERS:
            content = formatter(content)
        return content

    @validator('link_id', pre=False)
    def get_link(cls,
                 link_id: UUID | None,
                 values: dict[str, Any]) -> UUID | None:
        content = values['content']
        if link := LINK_PATTERN.search(content):
            return UUID(link.group(1))

        return None

    @validator('tags', pre=False)
    def get_tags(cls,
                 tags: list[str],
                 values: dict[str, Any]) -> list[str]:
        content = values['content']
        if tags := TAGS_PATTERN.findall(content):
            return [tag.strip().lower() for tag in tags]

        return []


class UpdateNote(Note):
    note_id: UUID

    def __init__(self,
                 tags: list[str],
                 link_id: UUID | None = None,
                 material_id: UUID = Form(...),
                 note_id: UUID = Form(...),
                 content: str = Form(...),
                 chapter: int = Form(0),
                 page: int = Form(0)):
        super().__init__(
            material_id=material_id,
            link_id=link_id,
            note_id=note_id,
            content=content,
            chapter=chapter,
            page=page,
            tags=tags,
        )


class DeleteNote(CustomBaseModel):
    note_id: UUID
    material_id: UUID

    def __init__(self,
                 material_id: UUID = Form(...),
                 note_id: UUID = Form(...)):
        super().__init__(
            material_id=material_id,
            note_id=note_id
        )
