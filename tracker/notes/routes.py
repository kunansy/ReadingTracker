import asyncio
from typing import Any, Iterable
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from tracker.common import manticoresearch, settings
from tracker.common.logger import logger
from tracker.materials import db as materials_db
from tracker.models import enums
from tracker.notes import db, schemas, speech_recognizer as recognizer


router = APIRouter(
    prefix="/notes",
    tags=['notes'],
)
templates = Jinja2Templates(directory="templates")


def _filter_notes(*,
                  notes: list[db.Note],
                  ids: Iterable[str]) -> list[db.Note]:
    notes_ = {
        note.note_id: note
        for note in notes
    }
    # order of search results saved, because ids sorted by weight
    return [
        notes_[note_id]
        for note_id in ids
        if note_id in notes_
    ]


def _find_tags_intersection(notes: list[db.Note], tags: set[str]) -> set[str]:
    return {
        note.note_id
        for note in notes
        # requested tags should be a subset of note tags
        if note.tags and note.tags >= tags
    }


def _highlight_snippets(notes: list[db.Note],
                        search_results: dict[str, manticoresearch.SearchResult]) -> None:
    for note in notes:
        result = search_results[note.note_id]
        note.highlight(result.replace_substring, result.snippet)


async def get_note_links(note: db.Note) -> dict[str, Any]:
    async with asyncio.TaskGroup() as tg:
        get_links_from_task = tg.create_task(db.get_links_from(note_id=note.note_id))
        if note.link_id:
            get_link_to_task = tg.create_task(db.get_note(note_id=note.link_id))
        else:
            get_link_to_task = tg.create_task(asyncio.sleep(1 / 1000, result=None))

    return {
        "from": get_links_from_task.result(),
        "to": get_link_to_task.result()
    }


@router.get('/', response_class=HTMLResponse)
async def get_notes(request: Request,
                    search: schemas.SearchParams = Depends()):
    material_id = search.material_id
    async with asyncio.TaskGroup() as tg:
        get_notes_task = tg.create_task(db.get_notes(material_id=material_id))
        get_titles_task = tg.create_task(db.get_material_with_notes_titles())
        get_material_types_task = tg.create_task(db.get_material_types())
        get_tags_task = tg.create_task(db.get_sorted_tags(material_id=material_id))

    notes = get_notes_task.result()

    if requested_tags := search.requested_tags():
        found_note_ids = _find_tags_intersection(notes, requested_tags)
        notes = _filter_notes(notes=notes, ids=found_note_ids)
    if query := search.query:
        search_results = await manticoresearch.search(query)
        notes = _filter_notes(notes=notes, ids=search_results.keys())
        _highlight_snippets(notes, search_results)

    chapters = db.get_distinct_chapters(notes)

    context: dict[str, Any] = {
        'request': request,
        'notes': notes,
        'titles': get_titles_task.result(),
        'material_types': get_material_types_task.result(),
        'chapters': chapters,
        'query': query,
        'DATE_FORMAT': settings.DATE_FORMAT,
        'tags': get_tags_task.result(),
        'tags_query': search.tags_query,
    }
    if material_id:
        context['material_id'] = material_id

    return templates.TemplateResponse("notes/notes.html", context)


@router.get('/note', response_class=HTMLResponse)
async def get_note(request: Request, note_id: UUID):
    if not (note := await db.get_note(note_id=note_id)):
        raise HTTPException(status_code=404, detail=f"Note id={note_id} not found")

    async with asyncio.TaskGroup() as tg:
        get_material_task = tg.create_task(materials_db.get_material(material_id=note.material_id))
        get_note_links_task = tg.create_task(get_note_links(note))

    if not (material := get_material_task.result()):
        raise HTTPException(status_code=404, detail=f"Material id={note.material_id} not found")

    context = note.dict() | {
        'request': request,
        'note_links': get_note_links_task.result(),
        'added_at': note.added_at.strftime(settings.DATETIME_FORMAT),
        'material_title': material.title,
        'material_authors': material.authors,
        'material_type': material.material_type,
        'material_pages': material.pages,
        'material_is_outlined': material.is_outlined,
    }

    return templates.TemplateResponse("notes/note.html", context)


@router.get('/add-view', response_class=HTMLResponse)
async def add_note_view(request: Request):
    material_id = request.cookies.get('material_id', '')

    async with asyncio.TaskGroup() as tg:
        get_titles_task = tg.create_task(db.get_material_titles())
        get_tags_task = tg.create_task(db.get_sorted_tags(material_id=material_id))

    context = {
        'request': request,
        'material_id': material_id,
        'material_type': request.cookies.get('material_type', enums.MaterialTypesEnum.book.name),
        'content': request.cookies.get('content', ''),
        'page': request.cookies.get('page', ''),
        'chapter': request.cookies.get('chapter', ''),
        'note_id': request.cookies.get('note_id', ''),
        'titles': get_titles_task.result(),
        'tags': get_tags_task.result()
    }
    return templates.TemplateResponse("notes/add_note.html", context)


@router.post('/add', response_class=RedirectResponse)
async def add_note(note: schemas.Note = Depends()):
    redirect_url = router.url_path_for(add_note_view.__name__)
    response = RedirectResponse(redirect_url, status_code=302)

    for key, value in note.dict(exclude={'content', 'tags', 'link_id'}).items():
        response.set_cookie(key, value, expires=3600)

    note_id = await db.add_note(
        material_id=note.material_id,
        link_id=note.link_id,
        content=note.content,
        chapter=note.chapter,
        page=note.page,
        tags=note.tags,
    )
    response.set_cookie('note_id', note_id, expires=5)
    if material_type := await db.get_material_type(material_id=note.material_id):
        response.set_cookie('material_type', material_type, expires=5)

    await manticoresearch.insert(note_id=note_id)

    return response


@router.get('/update-view', response_class=HTMLResponse)
async def update_note_view(note_id: UUID,
                           request: Request,
                           success: bool | None = None):
    context: dict[str, Any] = {
        'request': request,
    }

    if not (note := await db.get_note(note_id=note_id)):
        context['what'] = f"Note id='{note_id}' not found"
        return templates.TemplateResponse("errors/404.html", context)

    async with asyncio.TaskGroup() as tg:
        material_type = tg.create_task(db.get_material_type(material_id=note.material_id))
        get_tags_task = tg.create_task(db.get_sorted_tags(material_id=note.material_id))
        get_possible_links_task = tg.create_task(db.get_possible_links(note=note))

    context |= {
        'material_id': note.material_id,
        'material_type': material_type.result() or enums.MaterialTypesEnum.book.name,
        'note_id': note.note_id,
        'content': schemas.demark_note(note.content),
        'chapter': note.chapter,
        'page': note.page,
        'success': success,
        'tags': get_tags_task.result(),
    }
    if not note.link_id:
        context['possible_links'] = get_possible_links_task.result()

    return templates.TemplateResponse("notes/update_note.html", context)


@router.post('/update', response_class=RedirectResponse)
async def update_note(note: schemas.UpdateNote = Depends()):
    success = True
    note_id = str(note.note_id)

    try:
        await db.update_note(
            note_id=note_id,
            link_id=note.link_id,
            content=note.content,
            chapter=note.chapter,
            page=note.page,
            tags=note.tags,
        )

        await manticoresearch.update(note_id=note_id)
    except Exception as e:
        logger.error("Error updating note: %s", repr(e))
        success = False

    redirect_path = router.url_path_for(update_note_view.__name__)
    redirect_url = f"{redirect_path}?note_id={note.note_id}&{success=}"

    return RedirectResponse(redirect_url, status_code=302)


@router.delete('/delete', status_code=201)
async def delete_note(note_id: UUID = Body(embed=True)):
    note_id_str = str(note_id)

    async with asyncio.TaskGroup() as tg:
        tg.create_task(db.delete_note(note_id=note_id_str))
        tg.create_task(manticoresearch.delete(note_id=note_id_str))


@router.get('/links', response_class=HTMLResponse)
async def get_note_graph(note_id: UUID):
    notes = {
        note.note_id: note
        for note in await db.get_notes()
    }
    graph = db.link_notes(note_id=str(note_id), notes=notes)
    return db.create_graphic(graph)


@router.post("/transcript",
             response_model=schemas.TranscriptTextResponse)
async def transcript_speech(data: bytes = Body()):
    file = recognizer.get_file_content(data)
    path = recognizer.dump(file)
    recognizer.fix_file_format(path)

    logger.info("Start reading file")
    audio = recognizer.read_file(path)
    recognizer.remove(path)

    logger.info("File read, start recognition")
    if not (result := recognizer.recognize(audio)):
        raise HTTPException(status_code=400, detail="Could not recognize speech")

    logger.debug("Result got: %s", result)
    best = recognizer.get_best_result(result)

    logger.info("Transcript got: %s", best)

    return best


@router.get('/graph', response_class=HTMLResponse)
async def get_graph(request: Request):
    notes = await db.get_notes()
    graph = db.link_all_notes(notes)

    context = {
        'request': request,
        'graph': db.create_graphic(graph, height='80vh')
    }
    return templates.TemplateResponse("notes/graph.html", context)
