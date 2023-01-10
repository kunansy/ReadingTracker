import asyncio
from typing import Any, Iterable
from uuid import UUID

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from tracker.common import settings, manticoresearch
from tracker.common.log import logger
from tracker.models import enums
from tracker.notes import db, schemas


router = APIRouter(
    prefix="/notes",
    tags=['notes'],
    default_response_class=HTMLResponse
)
templates = Jinja2Templates(directory="templates")


def _filter_notes(*,
                  notes: list[db.Note],
                  ids: Iterable[str]) -> list[db.Note]:
    notes_ = {
        note.note_id: note
        for note in notes
    }
    # TODO: save order of search results,
    #  add _score field to Note model (?)
    return [
        notes_[note_id]
        for note_id in ids
        if note_id in notes_
    ]


@router.get('/')
async def get_notes(request: Request,
                    material_id: UUID | str | None = None,
                    query: str | None = None):
    async with asyncio.TaskGroup() as tg:
        if material_id:
            get_notes_task = tg.create_task(db.get_material_notes(material_id=material_id))
        else:
            get_notes_task = tg.create_task(db.get_notes())
        get_titles_task = tg.create_task(db.get_material_with_notes_titles())
        get_material_types_task = tg.create_task(db.get_material_types())

    notes = get_notes_task.result()

    if query:
        found_note_ids = await manticoresearch.search(query)
        notes = _filter_notes(notes=notes, ids=found_note_ids)

    chapters = db.get_distinct_chapters(notes)

    context = {
        'request': request,
        'notes': notes,
        'titles': get_titles_task.result(),
        'material_types': get_material_types_task.result(),
        'chapters': chapters,
        'query': query,
        'DATE_FORMAT': settings.DATE_FORMAT
    }
    if material_id:
        context['material_id'] = material_id

    return templates.TemplateResponse("notes/notes.html", context)


@router.get('/add-view')
async def add_note_view(request: Request):
    async with asyncio.TaskGroup() as tg:
        get_titles_task = tg.create_task(db.get_material_titles())
        get_links_task = tg.create_task(db.get_links())

    context = {
        'request': request,
        'material_id': request.cookies.get('material_id', ''),
        'material_type': request.cookies.get('material_type', enums.MaterialTypesEnum.book.name),
        'content': request.cookies.get('content', ''),
        'page': request.cookies.get('page', ''),
        'chapter': request.cookies.get('chapter', ''),
        'note_id': request.cookies.get('note_id', ''),
        'titles': get_titles_task.result(),
        'links': get_links_task.result()
    }
    return templates.TemplateResponse("notes/add_note.html", context)


@router.post('/add',
             response_class=RedirectResponse)
async def add_note(note: schemas.Note = Depends()):
    redirect_url = router.url_path_for(add_note_view.__name__)
    response = RedirectResponse(redirect_url, status_code=302)

    for key, value in note.dict(exclude={'content'}).items():
        response.set_cookie(key, value, expires=3600)

    note_id = await db.add_note(
        material_id=note.material_id,
        link_id=note.link_id,
        content=note.content,
        chapter=note.chapter,
        page=note.page,
        tags=note.tags,
    )
    response.set_cookie('note_id', str(note_id), expires=5)
    if material_type := await db.get_material_type(material_id=note.material_id):
        response.set_cookie('material_type', material_type, expires=5)

    await manticoresearch.insert(note_id=note_id)

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

    material_type = await db.get_material_type(material_id=note.material_id) \
                    or enums.MaterialTypesEnum.book.name # noqa
    links = await db.get_links()

    context |= {
        'material_id': note.material_id,
        'material_type': material_type,
        'note_id': note.note_id,
        'content': schemas.demark_note(note.content),
        'chapter': note.chapter,
        'page': note.page,
        'success': success,
        'links': links
    }
    return templates.TemplateResponse("notes/update_note.html", context)


@router.post('/update',
             response_class=RedirectResponse)
async def update_note(note: schemas.UpdateNote = Depends()):
    success = True
    try:
        await db.update_note(
            note_id=note.note_id,
            link_id=note.link_id,
            content=note.content,
            chapter=note.chapter,
            page=note.page,
            tags=note.tags,
        )
    except Exception as e:
        logger.error("Error updating note: %s", repr(e))
        success = False

    redirect_path = router.url_path_for(update_note_view.__name__)
    redirect_url = f"{redirect_path}?note_id={note.note_id}&{success=}"

    await manticoresearch.update(note_id=note.note_id)

    return RedirectResponse(redirect_url, status_code=302)


@router.post('/delete',
             response_class=RedirectResponse)
async def delete_note(note: schemas.DeleteNote = Depends()):
    await db.delete_note(note_id=note.note_id)

    redirect_path = router.url_path_for(get_notes.__name__)
    redirect_url = f"{redirect_path}?material_id={note.material_id}"

    await manticoresearch.delete(note_id=note.note_id)

    return RedirectResponse(redirect_url, status_code=302)
