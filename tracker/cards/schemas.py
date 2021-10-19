from typing import Optional

from pydantic import BaseModel, conint, constr, validator


def format_string(string: str,
                  ends: tuple[str, ...]) -> str:
    string = ' '.join(string.replace('\n', '<br/>').split())

    return f"{string[0].upper()}{string[1:]}" \
           f"{'.' * (not string.endswith(ends))}"


class Card(BaseModel):
    material_id: conint(gt=0) # type: ignore
    note_id: conint(gt=0) # type: ignore
    question: constr(strip_whitespace=True, min_length=1) # type: ignore
    answer: Optional[constr(strip_whitespace=True)] # type: ignore

    @validator('note_id')
    def validate_note_exists(cls,
                             note_id: int) -> int:
        # TODO
        # if not database.does_note_exist(note_id):
        #     raise ValueError(f"Note {note_id=} not found")

        return note_id

    @validator('question')
    def validate_question(cls,
                          question: str) -> str:
        return format_string(question, ('.', '?'))

    @validator('answer')
    def validate_answer(cls,  # type: ignore
                        answer: Optional[str]) -> Optional[str]:
        if answer:
            return format_string(answer, ('.',))
