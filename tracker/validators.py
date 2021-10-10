import datetime
from typing import Optional

from pydantic import constr, conint, validator
from pydantic import BaseModel

from tracker.common import database


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
