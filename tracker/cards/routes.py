from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from tracker.cards import db, schemas
from tracker.common import settings


router = APIRouter(prefix="/cards", tags=["cards"])
templates = Jinja2Templates(directory="templates")


@router.get("/list", response_class=HTMLResponse)
async def list_cards(request: Request):
    cards_list = await db.get_cards_list()
    total_cards_count = await db.get_cards_count()

    # TODO: menu with materials and titles
    context = {
        "request": request,
        "cards": cards_list,
        "DATE_FORMAT": settings.DATE_FORMAT,
        "total": total_cards_count,
    }
    return templates.TemplateResponse("cards/cards_list.html", context)


@router.get("/has-cards", response_model=schemas.GetHasCards)
async def has_cards(note_id: UUID):
    cards_count = await db.get_cards_count(note_id=note_id)

    return {
        "note_id": note_id,
        "has_cards": cards_count >= 1,
        "cards_count": cards_count,
    }
