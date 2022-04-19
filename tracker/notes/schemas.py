from uuid import UUID

from fastapi import Form
from pydantic import BaseModel, conint, constr, validator


PUNCTUATION_MAPPING = {
    "--": "—",
    "->": "→",
}
BOLD_MARKER = "font-weight-bold"
ITALIC_MARKER = "font-italic"


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


def _mark_bold(string: str) -> str:
    while '**' in string:
        string = string.replace("**", f'<span class="{BOLD_MARKER}">', 1)
        string = string.replace("**", f'</span class="{BOLD_MARKER}">', 1)
    return string


def _mark_italic(string: str) -> str:
    while '__' in string:
        string = string.replace("__", f'<span class="{ITALIC_MARKER}">', 1)
        string = string.replace("__", f'</span class="{ITALIC_MARKER}">', 1)
    return string


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
            material_id=material_id, content=content, chapter=chapter, page=page, **kwargs)

    @validator('content')
    def format_content(cls,
                       content: str) -> str:
        content = _add_dot(content)
        content = _replace_quotes(content)
        content = _up_first_letter(content)
        content = _mark_bold(content)
        content = _mark_italic(content)

        return _replace_punctuation(content)


class UpdateNote(Note):
    note_id: UUID

    def __init__(self,
                 material_id: UUID = Form(...),
                 note_id: UUID = Form(...),
                 content: str = Form(...),
                 chapter: int = Form(0),
                 page: int = Form(0)):
        super().__init__(
            material_id=material_id, note_id=note_id, content=content, chapter=chapter, page=page)
