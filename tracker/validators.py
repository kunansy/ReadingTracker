import datetime
from typing import Optional

from pydantic import constr, conint, validator
from pydantic import BaseModel as PydanticBaseModel

from src import db_api as db


class BaseModel(PydanticBaseModel):
    class Config:
        extra = 'forbid'
        allow_mutation = False


def validate_string(string: str,
                    ends: tuple[str, ...]) -> str:
    string = ' '.join(string.replace('\n', '<br/>').split())

    return f"{string[0].upper()}{string[1:]}" \
           f"{'.' * (not string.endswith(ends))}"


class Note(BaseModel):
    material_id: conint(gt=0)
    content: constr(strip_whitespace=True, min_length=1)
    chapter: conint(ge=0)
    page: conint(gt=0)

    @validator('material_id')
    def validate_material_assigned(cls,
                                   material_id: int) -> int:
        if not db.is_material_assigned(material_id):
            raise ValueError(f"Material {material_id=} is not assigned")

        return material_id

    @validator('page')
    def validate_page(cls,
                      page: int) -> int:
        # TODO: need an access to the material_id
        return page

    @validator('content')
    def validate_content(cls,
                         content: str) -> str:
        return validate_string(content, ('.',))

    def __str__(self) -> str:
        return repr(self)


class LogRecord(BaseModel):
    material_id: conint(gt=0)
    date: datetime.date
    count: conint(gt=0)

    @validator('date')
    def validate_date(cls,
                      date: datetime.date) -> datetime.date:
        if date > db.today():
            raise ValueError("You cannot set log to the future")
        return date

    @validator('material_id')
    def validate_material_reading(cls,
                                  material_id: int) -> int:
        if not db.is_material_reading(material_id):
            raise ValueError(f"Material {material_id=} is not reading")

        return material_id

    def __str__(self) -> str:
        return repr(self)


class Card(BaseModel):
    material_id: conint(gt=0)
    note_id: conint(gt=0)
    question: constr(strip_whitespace=True, min_length=1)
    answer: Optional[constr(strip_whitespace=True)]

    @validator('note_id')
    def validate_note_exists(cls,
                             note_id: int) -> int:
        if not db.does_note_exist(note_id):
            raise ValueError(f"Note {note_id=} not found")

        return note_id

    @validator('question')
    def validate_question(cls,
                          question: str) -> str:
        return validate_string(question, ('.', '?'))

    @validator('answer')
    def validate_answer(cls,
                        answer: Optional[str]) -> Optional[str]:
        if answer:
            return validate_string(answer, ('.',))

    def __str__(self) -> str:
        return repr(self)
