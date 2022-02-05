from collections import defaultdict
from uuid import UUID

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import conint

from tracker.common import settings
from tracker.notes import db


router = APIRouter(
    prefix="/notes",
    tags=['notes'],
    default_response_class=HTMLResponse
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


@router.get('/add-view')
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
async def add_note(material_id: UUID = Form(...),
                   content: str = Form(...),
                   chapter: conint(ge=0) = Form(0), # type: ignore
                   page: conint(ge=0) = Form(0)): # type: ignore
    await db.add_note(
        material_id=material_id, content=content, chapter=chapter, page=page
    )
    return RedirectResponse('/notes/add-view', status_code=302)
