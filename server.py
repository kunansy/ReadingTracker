#!/usr/bin/env python3
from collections import defaultdict
from typing import Any

import ujson
from pydantic import ValidationError
from sanic import Sanic, Request, response, HTTPResponse, exceptions
from sanic.log import logger as sanic_logger
from sanic_jinja2 import SanicJinja2
from sanic_session import Session

from src import logger as logger_, settings
from src import tracker as trc
from src import validators
from src import exceptions as ex


app = Sanic(__name__, log_config=logger_.LOGGING_CONFIG)
app.static('/static', './static')

session = Session(app)
jinja = SanicJinja2(app, session=session, enable_async=True)

log = trc.Log(full_info=True)
tracker = trc.Tracker(log)
cards = trc.Cards()


async def get_form_items(request: Request) -> dict[str, Any]:
    return {
        key: val[0]
        for key, val in request.form.items()
    }


@app.get('/notes')
@jinja.template('notes.html')
async def get_notes(request: Request) -> dict[str, Any]:
    material_id = request.args.get('material_id')

    all_notes = tracker.get_notes()
    notes = [
        note
        for note in all_notes
        if material_id is None or note.material_id == int(material_id)
    ]

    if not notes:
        jinja.flash(request, f'No notes {material_id=} found', 'error')
        return {}
    else:
        jinja.flash(request, f"{len(notes)} notes found", 'success')

    titles = tracker.get_material_titles(reading=True, completed=True)

    # show only the titles of materials that have notes
    all_ids = {
        note.material_id
        for note in all_notes
    }
    titles = {
        material_id: material_title
        for material_id, material_title in titles.items()
        if material_id in all_ids
    }

    # chapters of the shown materials,
    #  it should help to create menu
    chapters = defaultdict(set)
    for note in notes:
        chapters[note.material_id].add(note.chapter)

    return {
        'notes': notes,
        'titles': titles,
        'chapters': chapters,
        'DATE_FORMAT': settings.DATE_FORMAT
    }


@app.get('/notes/add')
@jinja.template('add_note.html')
async def add_note(request: Request) -> dict[str, Any]:
    return {
        'material_id': request.ctx.session.get('material_id', ''),
        'content': request.ctx.session.get('content', ''),
        'page': request.ctx.session.get('page', ''),
        'chapter': request.ctx.session.get('chapter', ''),
        'titles': tracker.get_material_titles(reading=True, completed=True)
    }


@app.post('/notes/add')
async def add_note(request: Request) -> HTTPResponse:
    form_items = await get_form_items(request)

    try:
        note = validators.Note(**form_items)
    except ValidationError as e:
        context = ujson.dumps(e.errors(), indent=4)
        sanic_logger.warning(f"Validation error:\n{context}")

        for error in e.errors():
            jinja.flash(request, f"{error['loc'][0]}: {error['msg']}", 'error')

        request.ctx.session.update(**form_items)
        return response.redirect('/notes/add')

    try:
        tracker.add_note(**note.dict())
    except ValueError as e:
        jinja.flash(request, str(e), 'error')
    else:
        jinja.flash(request, 'Note added', 'success')
    finally:
        request.ctx.session.update(**note.dict(exclude={'content'}))
        return response.redirect('/notes/add')


@app.get('/recall')
@jinja.template('recall.html')
async def recall(request: Request) -> dict[str, Any] or HTTPResponse:
    return {
        'card': cards.card,
        'titles': tracker.get_material_titles(reading=True, completed=True),
        'remains': cards.cards_remain()
    }


@app.post('/recall/<card_id:int>')
async def recall(request: Request,
                 card_id: int) -> HTTPResponse:
    try:
        result = request.form['result'][0]
    except KeyError:
        jinja.flash(request, "Wrong form structure", 'error')
        return response.redirect('/recall')

    cards.complete_card(result)
    jinja.flash(request, f"Card {card_id=} marked as {result}", result)

    return response.redirect('/recall')


@app.get('/recall/add')
@jinja.template('add_card.html')
async def add_card(request: Request) -> dict[str, Any]:
    material_id = request.args.get('material_id')

    notes = {
        note.id: note
        for note in tracker.get_notes()
        if material_id is None or note.material_id == int(material_id)
    }

    return {
        'material_id': material_id,
        'note_id': request.ctx.session.get('note_id', ''),
        'question': request.ctx.session.get('question', ''),
        'answer': request.ctx.session.get('answer', ''),
        'chapter': request.ctx.session.get('chapter', ''),
        'titles': tracker.get_material_titles(reading=True, completed=True),
        'notes': notes,
        'notes_with_cards': cards.notes_with_cards(material_id)
    }


@app.post('/recall/add')
async def add_card(request: Request) -> HTTPResponse:
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


@app.get('/recall/list')
@jinja.template('cards_list.html')
async def cards_list(request: Request) -> dict[str, Any]:
    return {
        'cards': cards.list(),
        'repeated_today': cards.repeated_today(),
        'DATE_FORMAT': settings.DATE_FORMAT,
        'titles': tracker.get_material_titles(completed=True, reading=True),
        'total': len(cards),
        'remains': cards.remains_for_today()
    }


@app.get('/')
async def home(request: Request) -> HTTPResponse:
    return response.redirect('/materials/queue')


@app.exception(ValidationError)
def validation_error_handler(request: Request,
                             exception: ValidationError) -> HTTPResponse:
    context = ujson.dumps(exception.errors(), indent=4)

    sanic_logger.error(f"Validation error was not handled:\n{context}")
    return response.json(exception.errors(), status=400, indent=4)


@app.exception(exceptions.NotFound,
               ex.BaseNotFoundError)
async def not_found(request: Request,
                    exception: Exception) -> dict[str, Any]:
    args = '; '.join(
        str(arg)
        for arg in exception.args
    )

    sanic_logger.error(f"Not found error: {args}")
    return await jinja.render_async(
        'errors/404.html', request, what=args, status=404)


@app.exception(ex.BaseTrackerError)
@jinja.template('errors/500.html')
async def error_handler(request: Request,
                        exception: Exception) -> dict[str, Any]:
    try:
        ex_json = exception.json()
    except:
        ex_json = ''

    context = {
        "wrong_request": request.url,
        "error": {
            "type": exception.__class__.__name__,
            "text": str(exception),
            "args": exception.args,
            "json": ex_json
        }
    }

    sanic_logger.error(ujson.dumps(context, indent=4))
    return await jinja.render_async(
        'errors/500.html', request, **context, status=500)


if __name__ == "__main__":
    app.run(
        port=8080,
        debug=True,
        workers=1,
        access_log=False
    )
