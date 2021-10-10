from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from tracker.common import settings
from tracker.cards import db, schemas


router = APIRouter(
    prefix="/cards",
    tags=["cards"]
)
templates = Jinja2Templates(directory="templates")


@router.get('/', response_class=HTMLResponse)
async def recall(request: Request):
    current_card = await db.get_current_card()
    titles = await db.get_material_titles()
    cards_remains = await db.get_cards_remains()

    context = {
        'request': request,
        'card': current_card,
        'titles': titles,
        'remains': cards_remains
    }
    return templates.TemplateResponse("recall.html", context)


@router.post('/{card_id}')
async def recall_card(request: Request,
                      card_id: int,
                      result=Body(...)):
    await db.complete_card(result)
    jinja.flash(request, f"Card {card_id=} marked as {result}", result)

    return RedirectResponse('/recall')


@router.get('/add', response_class=HTMLResponse)
async def add_card_view(request: Request):
    material_id = request.args.get('material_id')
    titles = await db.get_material_titles()
    notes_with_cards = await db.get_cards_with_notes()

    notes = {
        note.id: note
        for note in await db.get_notes()
        if material_id is None or note.material_id == int(material_id)
    }

    context = {
        'request': request,
        'material_id': material_id,
        'note_id': request.ctx.session.get('note_id', ''),
        'question': request.ctx.session.get('question', ''),
        'answer': request.ctx.session.get('answer', ''),
        'chapter': request.ctx.session.get('chapter', ''),
        'titles': titles,
        'notes': notes,
        'notes_with_cards': notes_with_cards
    }
    return templates.TemplateResponse("add_recall.html", context)


@router.post('/add')
async def add_card(request: Request,
                   card: schemas.Card):
    await db.add_card(**card.dict())
    jinja.flash(request, "Card added", 'success')

    request.ctx.session.pop('question')
    request.ctx.session.pop('note_id')

    url = f"/recall/add?material_id={card.material_id}#note-{card.note_id}"
    return RedirectResponse(url)


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
