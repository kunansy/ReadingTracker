from uuid import UUID

from fastapi import Form
from pydantic import BaseModel, conint, constr, validator


PUNCTUATION_MAPPING = {
    "--": "—",
    "->": "→",
}


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
