import datetime
from typing import Optional

from pydantic import BaseModel, constr, conint, validator

from src import db_api as db


def validate_string(string: str,
                    ends: tuple[str, ...]) -> str:
    string = ' '.join(string.replace('\n', '<br/>').split())

    return f"{string[0].upper()}{string[1:]}" \
           f"{'.' * (not string.endswith(ends))}"


def validate_material_exists(material_id: int) -> int:
    if not db.does_material_exist(material_id):
        raise ValueError(f"Material {material_id=} not found")

    return material_id


class Material(BaseModel):
    class Config:
        extra = 'forbid'

    title: constr(strip_whitespace=True, min_length=1)
    authors: constr(strip_whitespace=True, min_length=1)
    pages: conint(gt=0)
    tags: constr(strip_whitespace=True)

    @validator('title', 'authors', 'tags')
    def validate_title(cls,
                       item: str) -> str:
        if '"' in item or '«' in item or '»' in item:
            raise ValueError("The brackets is unexpected here")
        return item

    def __repr__(self) -> str:
        fields = ', '.join(
            f"{key}='{val}'"
            for key, val in self.dict().items()
        )
        return f"{self.__class__.__name__}({fields})"

    def __str__(self) -> str:
        return repr(self)


class Note(BaseModel):
    class Config:
        extra = 'forbid'

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

    def __repr__(self) -> str:
        fields = ', '.join(
            f"{key}='{val}'"
            for key, val in self.dict().items()
        )
        return f"{self.__class__.__name__}({fields})"

    def __str__(self) -> str:
        return repr(self)


class LogRecord(BaseModel):
    class Config:
        extra = 'forbid'

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

    def __repr__(self) -> str:
        data = ', '.join(
            f"{key}={value}"
            for key, value in self.dict().items()
        )
        return f"{self.__class__.__name__}({data})"

    def __str__(self) -> str:
        return repr(self)


class Card(BaseModel):
    class Config:
        extra = 'forbid'

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

    def __repr__(self) -> str:
        data = ', '.join(
            f"{key}={value}"
            for key, value in self.dict().items()
        )
        return f"{self.__class__.__name__}({data})"

    def __str__(self) -> str:
        return repr(self)
