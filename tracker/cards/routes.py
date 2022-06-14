from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from tracker.cards import db
from tracker.common import settings


router = APIRouter(
    prefix="/cards",
    tags=["cards"]
)
templates = Jinja2Templates(directory="templates")


@router.get('/list', response_class=HTMLResponse)
async def list_cards(request: Request):
    cards_list = await db.get_cards_list()
    total_cards_count = await db.get_cards_count()

    # TODO: menu with materials and titles
    context = {
        'request': request,
        'cards': cards_list,
        'DATE_FORMAT': settings.DATE_FORMAT,
        'total': total_cards_count,
    }
    return templates.TemplateResponse("cards/cards_list.html", context)
