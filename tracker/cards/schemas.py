import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import BeforeValidator, NonNegativeInt, model_validator

from tracker.common.schemas import CustomBaseModel, skip_empty_value
from tracker.models import enums


class GetHasCards(CustomBaseModel):
    note_id: UUID | None
    material_id: UUID | None
    has_cards: bool
    cards_count: NonNegativeInt

    @model_validator(mode="after")
    def validate_ids(self) -> Self:
        assert self.material_id or self.note_id is not None
        return self


class Card(CustomBaseModel):
    material_id: UUID
    note_id: UUID
    question: str
    answer: Annotated[str | None, BeforeValidator(skip_empty_value)] = None


class ListCardsItem(CustomBaseModel):
    card_id: UUID
    note_id: UUID
    material_id: UUID
    question: str
    answer: str | None
    added_at: datetime.datetime
    note_title: str | None
    note_content: str
    note_chapter: str
    note_page: int
    material_title: str
    material_authors: str
    material_type: enums.MaterialTypesEnum


class ListCardsResponse(CustomBaseModel):
    items: list[ListCardsItem]


class CreateCardRequest(CustomBaseModel):
    material_id: UUID
    note_id: UUID
    question: str
    answer: str | None = None


class CreateCardResponse(CustomBaseModel):
    card_id: UUID


class ListMaterialsWithCardsResponse(CustomBaseModel):
    items: dict[UUID, str]


class ListNotesWithCardsResponse(CustomBaseModel):
    items: list[UUID]
