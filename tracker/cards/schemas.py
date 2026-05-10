import datetime
from uuid import UUID

from tracker.common.schemas import CustomBaseModel
from tracker.models import enums


class _ListCardsItem(CustomBaseModel):
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
    items: list[_ListCardsItem]


class CreateCardRequest(CustomBaseModel):
    material_id: UUID
    note_id: UUID
    question: str
    answer: str | None = None


class CreateCardResponse(CustomBaseModel):
    card_id: UUID


class ListNotesWithCardsResponse(CustomBaseModel):
    items: list[UUID]
