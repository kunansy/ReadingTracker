import re
from uuid import UUID

from fastapi import Form
from pydantic import BaseModel, conint, constr, validator


PUNCTUATION_MAPPING = {
    "--": "—",
    "->": "→",
    "<-": "←",
    "<->": "↔",
}
BOLD_MARKER = "font-weight-bold"
ITALIC_MARKER = "font-italic"
CODE_MARKER = "font-code"


def _replace_quotes(string: str) -> str:
    while '"' in string:
        string = string.replace('"', "«", 1)
        string = string.replace('"', "»", 1)
    return string


def _add_dot(string: str) -> str:
    if not string.endswith(('.', '?', '!')):
        return f"{string}."
    return string


def _up_first_letter(string: str) -> str:
    return f"{string[0].upper()}{string[1:]}"


def _replace_punctuation(string: str) -> str:
    for src, dst in PUNCTUATION_MAPPING.items():
        string = string.replace(src, dst)
    return string


def _replace_new_lines(string: str) -> str:
    return string.replace("\n", "<br/>")


def _mark_bold(string: str) -> str:
    while '**' in string:
        # don't add quotes around class names, because
        # quotes will be replaced by the quotes formatter
        string = string.replace("**", f"<span class={BOLD_MARKER}>", 1)
        string = string.replace("**", "</span>", 1)
    return string


def _mark_italic(string: str) -> str:
    while '__' in string:
        string = string.replace("__", f"<span class={ITALIC_MARKER}>", 1)
        string = string.replace("__", "</span>", 1)
    return string


def _mark_code(string: str) -> str:
    while '`' in string:
        string = string.replace("`", f"<span class={CODE_MARKER}>", 1)
        string = string.replace("`", "</span>", 1)
    return string


def _demark_bold(string: str) -> str:
    pattern = re.compile(f'<span class="?{BOLD_MARKER}"?>(.*?)</span>')

    while pattern.search(string):
        string = pattern.sub(r'**\1**', string)
    return string


def _demark_italic(string: str) -> str:
    pattern = re.compile(f'<span class="?{ITALIC_MARKER}"?>(.*?)</span>')

    # TODO: replace while with if?
    while pattern.search(string):
        string = pattern.sub(r'__\1__', string)
    return string


def _demark_code(string: str) -> str:
    pattern = re.compile(f'<span class="?{CODE_MARKER}"?>(.*?)</span>')

    while pattern.search(string):
        string = pattern.sub(r'`\1`', string)
    return string


def _dereplace_new_lines(string: str) -> str:
    return re.sub(r'<br/?>', '\n', string)


def demark_note(string: str) -> str:
    """ to show the note in update form """
    string = _demark_bold(string)
    string = _demark_italic(string)
    string = _demark_code(string)
    string = _dereplace_new_lines(string)
    return string


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


class Note(BaseModel):
    material_id: UUID
    content: constr(strip_whitespace=True)
    chapter: conint(ge=0) = 0
    page: conint(ge=0) = 0

    def __init__(self,
                 material_id: UUID = Form(...),
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

    @validator('content')
    def format_content(cls,
                       content: str) -> str:
        for formatter in NOTES_FORMATTERS:
            content = formatter(content)
        return content


class UpdateNote(Note):
    note_id: UUID

    def __init__(self,
                 material_id: UUID = Form(...),
                 note_id: UUID = Form(...),
                 content: str = Form(...),
                 chapter: int = Form(0),
                 page: int = Form(0)):
        super().__init__(
            material_id=material_id,
            note_id=note_id,
            content=content,
            chapter=chapter,
            page=page
        )
