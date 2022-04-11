from uuid import UUID

from fastapi import Form
from pydantic import BaseModel, conint, constr, validator


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
    def validate_content(cls,
                         content: str) -> str:
        if not content.endswith(('.', '?', '!')):
            content = f"{content}."

        return content\
            .replace('--', "–")\
            .replace('->', "→")


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
