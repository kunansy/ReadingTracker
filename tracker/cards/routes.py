from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from tracker.common import settings
from tracker.cards import db, schemas


router = APIRouter(
    prefix="/cards",
    tags=["cards"]
)


@router.get('/', response_class=HTMLResponse)
async def recall(request: Request):
    return {
        'request': request,
        'card': cards.card,
        'titles': tracker.get_material_titles(reading=True, completed=True),
        'remains': cards.cards_remain()
    }


@router.post('/{card_id}')
async def recall_card(request: Request,
                      card_id: int):
    try:
        result = request.form['result'][0]
    except KeyError:
        jinja.flash(request, "Wrong form structure", 'error')
        return response.redirect('/recall')

    cards.complete_card(result)
    jinja.flash(request, f"Card {card_id=} marked as {result}", result)

    return response.redirect('/recall')


@router.get('/add', response_class=HTMLResponse)
async def add_card_view(request: Request):
    material_id = request.args.get('material_id')

    notes = {
        note.id: note
        for note in tracker.get_notes()
        if material_id is None or note.material_id == int(material_id)
    }

    return {
        'request': request,
        'material_id': material_id,
        'note_id': request.ctx.session.get('note_id', ''),
        'question': request.ctx.session.get('question', ''),
        'answer': request.ctx.session.get('answer', ''),
        'chapter': request.ctx.session.get('chapter', ''),
        'titles': tracker.get_material_titles(reading=True, completed=True),
        'notes': notes,
        'notes_with_cards': cards.notes_with_cards(material_id)
    }


@router.post('/add')
async def add_card(request: Request,
                   card: schemas.Card):
    form_items = await get_form_items(request)

    try:
        card = validators.Card(**form_items)
    except ValidationError as e:
        context = ujson.dumps(e.errors(), indent=4)
        sanic_logger.warning(f"Validation error:\n{context}")

        for error in e.errors():
            jinja.flash(request, f"{error['loc'][0]}: {error['msg']}", 'error')

        request.ctx.session.update(**form_items)

        if material_id := form_items.get('material_id', ''):
            material_id = f"?{material_id=}"
        if note_id := form_items.get('note_id', ''):
            note_id = f"#note-{note_id}"

        url = f"/recall/add{material_id}{note_id}"
        return response.redirect(url)

    cards.add_card(**card.dict())
    jinja.flash(request, "Card added", 'success')

    request.ctx.session.pop('question')
    request.ctx.session.pop('note_id')

    url = f"/recall/add?material_id={card.material_id}#note-{card.note_id}"
    return response.redirect(url)


@router.get('/list', response_class=HTMLResponse)
async def list_cards(request: Request):
    return {
        'request': request,
        'cards': cards.list(),
        'repeated_today': cards.repeated_today(),
        'DATE_FORMAT': settings.DATE_FORMAT,
        'titles': tracker.get_material_titles(completed=True, reading=True),
        'total': len(cards),
        'remains': cards.remains_for_today()
    }
