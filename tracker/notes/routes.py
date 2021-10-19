from collections import defaultdict

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from tracker.common import settings
from tracker.notes import db, schemas


router = APIRouter(
    prefix="/notes",
    tags=['notes']
)
templates = Jinja2Templates(directory="templates")


@router.get('/')
async def get_notes(request: Request,
                    material_id: str = Query(None)):
    all_notes = await db.get_notes()
    notes = [
        note
        for note in all_notes
        if material_id is None or note.material_id == material_id
    ]

    if not notes:
        return {}

    titles = await db.get_material_titles()

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

    context = {
        'request': request,
        'notes': notes,
        'titles': titles,
        'chapters': chapters,
        'DATE_FORMAT': settings.DATE_FORMAT
    }
    return templates.TemplateResponse("notes.html", context)


@router.get('/add')
async def add_note_view(request: Request):
    titles = await db.get_material_titles()

    context = {
        'request': request,
        'material_id': request.cookies.get('material_id', ''),
        'content': request.cookies.get('content', ''),
        'page': request.cookies.get('page', ''),
        'chapter': request.cookies.get('chapter', ''),
        'titles': titles
    }
    return templates.TemplateResponse("add_note.html", context)


@router.post('/add')
async def add_note(note: schemas.Note,
                   response: Response):
    await db.add_note(note=note)

    for key, value in note.dict(exclude={'content'}):
        response.set_cookie(key=key, value=value)

    return RedirectResponse('/notes/add')
