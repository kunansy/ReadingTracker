from collections import defaultdict
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from tracker.common import settings
from tracker.common.log import logger
from tracker.notes import db, schemas


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


@router.post('/add',
             response_class=RedirectResponse)
async def add_note(note: schemas.Note = Depends()):
    response = RedirectResponse('/notes/add-view', status_code=302)

    for key, value in note.dict(exclude={'content'}).items():
        response.set_cookie(key, value, expires=3600)

    await db.add_note(
        material_id=note.material_id,
        content=note.content,
        chapter=note.chapter,
        page=note.page
    )

    return response


@router.get('/update-view')
async def update_note_view(note_id: UUID,
                           request: Request,
                           success: bool | None = None):
    context: dict[str, Any] = {
        'request': request,
    }

    if not (note := await db.get_note(note_id=note_id)):
        context['what'] = f"Note id='{note_id}' not found"
        return templates.TemplateResponse("errors/404.html", context)

    context = {
        **context,
        'material_id': note['material_id'],
        'note_id': note['note_id'],
        'content': schemas.demark_note(note['content']),
        'chapter': note['chapter'],
        'page': note['page'],
        'success': success
    }
    return templates.TemplateResponse("update_note.html", context)


@router.post('/update',
             response_class=RedirectResponse)
async def update_note(note: schemas.UpdateNote = Depends()):
    success = True
    try:
        await db.update_note(
            note_id=note.note_id,
            content=note.content,
            chapter=note.chapter,
            page=note.page
        )
    except Exception as e:
        logger.error("Error updating note: %s", repr(e))
        success = False

    redirect_url = f'/notes/update-view?note_id={note.note_id}&{success=}'
    response = RedirectResponse(redirect_url, status_code=302)
    return response
