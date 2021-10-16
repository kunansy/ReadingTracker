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
    repeated_today = await db.get_repeated_today_cards_count()
    remains_for_today = await db.get_remains_for_today_cards_count()
    total_cards_count = await db.get_total_cards_count()
    titles = await db.get_material_titles()

    context = {
        'request': request,
        'cards': cards_list,
        'repeated_today': repeated_today,
        'DATE_FORMAT': settings.DATE_FORMAT,
        'titles': titles,
        'total': total_cards_count,
        'remains': remains_for_today
    }
    return templates.TemplateResponse("list_cards.html", context)
