from uuid import UUID

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
