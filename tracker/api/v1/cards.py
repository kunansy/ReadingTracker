from uuid import UUID

from fastapi import APIRouter

from tracker.cards import db, schemas


router = APIRouter(prefix="/cards", tags=["cards-api"])


@router.get("/", response_model=schemas.ListCardsResponse)
async def list_cards(material_id: UUID | None = None):
    items = await db.get_cards(material_id=material_id)
    return {
        "items": items,
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

@router.get("/materials-titles", response_model=schemas.ListMaterialsWithCardsResponse)
async def list_materials_with_cards():
    items = await db.list_materials_with_cards()
    return {
        "items": items,
    }
