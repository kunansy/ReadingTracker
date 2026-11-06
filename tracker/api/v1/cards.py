from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from tracker.cards import db, schemas
from tracker.common.pagination import PageParams


router = APIRouter(prefix="/cards", tags=["cards-api"])


@router.get("/", response_model=schemas.ListCardsResponse)
async def list_cards(
    params: Annotated[PageParams, Depends()],
    material_id: UUID | None = None,
):
    page = await db.get_cards_page(material_id=material_id, params=params)
    return {
        "items": page.items,
        "next_token": page.next_token,
        "total_count": page.total_count,
    }


@router.post("/", status_code=201, response_model=schemas.CreateCardResponse)
async def create_card(card: schemas.CreateCardRequest):
    card_id = await db.add_card(
        material_id=card.material_id,
        note_id=card.note_id,
        question=card.question,
        answer=card.answer,
    )

    return {
        "card_id": card_id,
    }


@router.get("/notes-with-cards", response_model=schemas.ListNotesWithCardsResponse)
async def list_notes_with_cards(material_id: UUID | None = None):
    items = await db.get_notes_with_cards(material_id=material_id)

    return {
        "items": sorted(items),
    }
