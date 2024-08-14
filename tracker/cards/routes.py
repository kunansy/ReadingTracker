import asyncio
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
    async with asyncio.TaskGroup() as tg:
        cards_list_task = tg.create_task(db.get_cards_list())
        total_cards_count_task = tg.create_task(db.get_cards_count())

    cards = cards_list_task.result()

    # TODO: menu with materials and titles
    context = {
        "request": request,
        "cards": cards,
        "DATE_FORMAT": settings.DATE_FORMAT,
        "total": total_cards_count_task.result(),
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
