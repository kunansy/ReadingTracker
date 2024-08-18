from uuid import UUID

from fastapi import Form
from pydantic import NonNegativeInt

from tracker.common.schemas import CustomBaseModel


class GetHasCards(CustomBaseModel):
    note_id: UUID
    has_cards: bool
    cards_count: NonNegativeInt


class Card(CustomBaseModel):
    material_id: UUID
    note_id: UUID
    question: str
    answer: str | None

    def __init__(
        self,
        material_id: UUID = Form(...),
        note_id: UUID = Form(...),
        question: str = Form(...),
        answer: str | None = Form(None),
    ):
        super().__init__(
            material_id=material_id,
            note_id=note_id,
            question=question,
            answer=answer,
        )
