import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from tracker.common import database, kafka, manticoresearch
from tracker.common.pagination import PageParams
from tracker.materials import db as materials_db
from tracker.notes import db, schemas
from tracker.notes.listing import build_notes_search_result


router = APIRouter(prefix="/notes", tags=["notes-api"])


# TODO: split the request
@router.get("/search", response_model=schemas.SearchNotesResponse)
async def notes_search_json(
    search: Annotated[schemas.SearchParams, Depends()],
    params: Annotated[PageParams, Depends()],
):
    # TODO: get cards count
    ctx = await build_notes_search_result(search=search, params=params)
    notes = ctx["notes"]
    chapters = ctx["chapters"]
    titles = ctx["titles"]
    material_types = ctx["material_types"]
    material_notes = ctx["material_notes"]

    return {
        "notes": [
            schemas.SearchNotesItem.model_validate(n, from_attributes=True) for n in notes
        ],
        "total_count": ctx["total_count"],
        "titles": titles,
        "material_types": material_types,
        "material_notes": material_notes,
        "chapters": chapters,
        "query": ctx["query"],
        "tags": ctx["tags"],
        "tags_query": ctx["tags_query"],
        "next_token": ctx["next_token"],
        "page_size": ctx["page_size"],
        "material_id": ctx["material_id"],
    }


@router.get("/graph", response_model=schemas.GetNotesGraphResponse)
async def notes_graph_json(material_id: UUID | None = None):
    async with asyncio.TaskGroup() as tg:
        get_notes_task = tg.create_task(db.get_notes())
        get_titles_task = tg.create_task(db.get_material_titles())
        if material_id:
            get_material_notes_task = tg.create_task(
                db.get_notes(material_id=material_id),
            )
        else:
            get_material_notes_task = tg.create_task(
                asyncio.sleep(1 / 100_000, result=[]),
            )

    notes = get_notes_task.result()
    titles = get_titles_task.result()

    if material_id:
        notes_dict = {note.note_id: note for note in notes}
        material_notes = {note.note_id for note in get_material_notes_task.result()}
        graph = db.create_material_graph(
            material_id=material_id,
            material_notes=material_notes,
            notes=notes_dict,
        )
    else:
        graph = db.link_all_notes(notes)

    iframe_srcdoc = db.create_graphic(graph, height="80vh")
    return {
        "iframe_srcdoc": iframe_srcdoc,
        "titles": titles,
        "material_id": material_id,
    }


# TODO: split the request
@router.get("/meta", response_model=schemas.GetNotesMetaResponse, deprecated=True)
async def get_notes_meta(material_id: UUID | None = None):
    async with asyncio.TaskGroup() as tg:
        get_titles_task = tg.create_task(db.get_material_titles())
        get_tags_task = tg.create_task(db.get_sorted_tags(material_id=material_id))

    return {
        "titles": get_titles_task.result(),
        "tags": get_tags_task.result(),
    }


async def _check_note_refs(*, material_id: UUID, link_id: UUID | None) -> None:
    await materials_db.get_material_api(material_id=material_id)
    if link_id:
        await db.get_note(note_id=link_id)


@router.post("/add", status_code=201, response_model=schemas.AddNoteResponse)
async def add_note(note: schemas.AddNoteRequest):
    await _check_note_refs(material_id=note.material_id, link_id=note.link_id)

    note_id = await db.insert_note(
        material_id=note.material_id,
        link_id=note.link_id,
        title=note.title,
        content=note.content,
        chapter=note.chapter,
        page=note.page,
        tags=note.tags,
    )
    await manticoresearch.insert_note(
        note_id=note_id,
        content=note.content,
        added_at=database.utcnow(),
    )
    return {"note_id": note_id}


@router.patch("/{note_id}", status_code=204)
async def update_note(note_id: UUID, body: schemas.UpdateNoteRequest):
    await _check_note_refs(material_id=body.material_id, link_id=body.link_id)
    if body.link_id and await db.is_link_cyclic(note_id=note_id, link_id=body.link_id):
        raise HTTPException(status_code=400, detail="Link would create a cycle")

    await db.update_note(
        note_id=note_id,
        material_id=body.material_id,
        link_id=body.link_id,
        title=body.title,
        content=body.content,
        chapter=body.chapter,
        page=body.page,
        tags=body.tags,
    )
    await manticoresearch.update_content(
        note_id=note_id,
        content=body.content,
        added_at=database.utcnow(),
    )


@router.get("/autocompletion", response_model=schemas.AutocompletionResponse)
async def get_autocompletion(query: str, limit: int = 10):
    autocompletions = await manticoresearch.autocompletion(query=query, limit=limit)

    return {"autocompletions": autocompletions}


@router.get("/tags", response_model=schemas.NoteTagsResponse)
async def get_note_tags(material_id: UUID | None = None):
    tags = await db.get_sorted_tags(material_id=material_id)

    return {"tags": tags}


@router.get("/possible-links", response_model=schemas.ListPossibleNoteLinksResponse)
async def list_possible_note_links(note_id: UUID):
    note = await db.get_note(note_id=note_id)

    possible_links = await db.get_possible_links(note_id=note_id, note_tags=note.tags)

    return {"items": possible_links}


@router.get("/links-network", response_class=HTMLResponse)
async def get_note_links_network(note_id: UUID):
    await db.get_note(note_id=note_id)
    # TODO: try to refactor without full listing
    notes = {note.note_id: note for note in await db.get_notes()}
    graph = db.link_notes(note_id=note_id, notes=notes)
    return db.create_graphic(graph)


@router.get("/links", response_model=schemas.GetNoteLinksResponse)
async def get_note_links(note_id: UUID, params: Annotated[PageParams, Depends()]):
    note = await db.get_note(note_id=note_id)

    async with asyncio.TaskGroup() as tg:
        get_links_from_task = tg.create_task(
            db.get_links_from_page(note_id=note_id, params=params),
        )
        if note.link_id:
            get_link_to_task: asyncio.Task[db.Note | None] = tg.create_task(
                db.get_note(note_id=note.link_id),
            )
        else:
            get_link_to_task = tg.create_task(asyncio.sleep(1 / 1000, result=None))

    links_from = get_links_from_task.result()
    return {
        "links_from": links_from.items,
        "link_to": get_link_to_task.result(),
        "next_token": links_from.next_token,
        "total_count": links_from.total_count,
    }


@router.get("/{note_id}", response_model=schemas.GetNoteResponse)
async def get_note(note_id: UUID):
    note = await db.get_note(note_id=note_id)

    return {"note": note}


@router.delete("/{note_id}", status_code=204)
async def delete_note(note_id: UUID):
    if links_count := await db.count_links_to(note_id=note_id):
        raise HTTPException(
            status_code=409,
            detail=f"Note is linked from {links_count} notes",
        )

    await db.delete_note(note_id=note_id)


@router.post("/{note_id}/restore", status_code=204)
async def restore_note(note_id: UUID):
    await db.restore_note(note_id=note_id)


@router.post("/{note_id}/repeat-queue", status_code=204)
async def insert_to_repeat_queue(note_id: UUID):
    await db.get_note(note_id=note_id)
    await kafka.repeat_note(note_id)
