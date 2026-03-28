from typing import TYPE_CHECKING, Annotated, Self

from pydantic import BeforeValidator, NonNegativeInt, model_validator

from tracker.common.schemas import CustomBaseModel, skip_empty_value


if TYPE_CHECKING:
    from uuid import UUID


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
