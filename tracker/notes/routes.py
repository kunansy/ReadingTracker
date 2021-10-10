from fastapi import APIRouter, Request

from tracker.notes import schemas


router = APIRouter(
    prefix="/notes",
    tags=['notes']
)


@router.get('/')
async def get_notes(request: Request):
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
        'request': request,
        'notes': notes,
        'titles': titles,
        'chapters': chapters,
        'DATE_FORMAT': settings.DATE_FORMAT
    }


@router.get('/add')
async def add_note_view(request: Request):
    return {
        'request': request,
        'material_id': request.ctx.session.get('material_id', ''),
        'content': request.ctx.session.get('content', ''),
        'page': request.ctx.session.get('page', ''),
        'chapter': request.ctx.session.get('chapter', ''),
        'titles': tracker.get_material_titles(reading=True, completed=True)
    }


@router.post('/add')
async def add_note(request: Request,
                   note: schemas.Note):
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
