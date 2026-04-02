import asyncio
from collections import defaultdict
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import NonNegativeInt

from tracker.common import manticoresearch
from tracker.models import enums
from tracker.notes import cached, db, schemas
from tracker.notes.listing import build_notes_search_result


router = APIRouter(prefix="/notes", tags=["notes-api"])


def _note_list_item(note: db.Note) -> dict[str, Any]:
    return {
        "note_id": str(note.note_id),
        "material_id": str(note.material_id),
        "title": note.title,
        "content_html": note.content_html,
        "tags_html": note.tags_html,
        "link_html": note.link_html,
        "chapter": note.chapter,
        "chapter_int": note.chapter_int,
        "page": note.page,
        "links_count": note.links_count,
    }


def _serialize_chapters(chapters: defaultdict[UUID, list[str]]) -> dict[str, list[str]]:
    return {str(k): v for k, v in chapters.items()}


def _serialize_titles(titles: dict[UUID, str]) -> dict[str, str]:
    return {str(k): v for k, v in titles.items()}


def _serialize_material_types(
    types_: dict[str, enums.MaterialTypesEnum],
) -> dict[str, str]:
    return dict(types_.items())


def _serialize_material_notes(counts: dict[UUID, int]) -> dict[str, int]:
    return {str(k): v for k, v in counts.items()}


@router.get("/search")
async def notes_search_json(
    search: Annotated[schemas.SearchParams, Depends()],
    page: NonNegativeInt = 1,
    page_size: NonNegativeInt = 10,
):
    ctx = await build_notes_search_result(
        search=search,
        page=page,
        page_size=page_size,
    )
    notes = ctx["notes"]
    chapters = ctx["chapters"]
    titles = ctx["titles"]
    material_types = ctx["material_types"]
    material_notes = ctx["material_notes"]

    return {
        "notes": [_note_list_item(n) for n in notes],
        "total_count": ctx["total_count"],
        "titles": _serialize_titles(titles),
        "material_types": _serialize_material_types(material_types),
        "material_notes": _serialize_material_notes(material_notes),
        "chapters": _serialize_chapters(chapters),
        "query": ctx["query"],
        "tags": ctx["tags"],
        "tags_query": ctx["tags_query"],
        "current_page": ctx["current_page"],
        "page_size": ctx["page_size"],
        "material_id": str(ctx["material_id"]) if ctx["material_id"] else None,
    }


@router.get("/graph")
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
        "titles": _serialize_titles(titles),
        "material_id": str(material_id) if material_id else None,
    }


@router.get("/meta", response_model=schemas.GetNotesMetaResponse)
async def get_notes_meta(material_id: UUID | None = None):
    async with asyncio.TaskGroup() as tg:
        get_titles_task = tg.create_task(db.get_material_titles())
        get_tags_task = tg.create_task(db.get_sorted_tags(material_id=material_id))

    return {
        "titles": get_titles_task.result(),
        "tags": get_tags_task.result(),
    }


@router.post("/add", status_code=201)
async def add_note_json(note: schemas.Note):
    note_id = await db.add_note(
        material_id=note.material_id,
        link_id=note.link_id,
        title=note.title,
        content=note.content,
        chapter=note.chapter,
        page=note.page,
        tags=note.tags,
    )
    return {"ok": True, "note_id": note_id}


@router.get("/autocompletion", response_model=schemas.AutocompletionResponse)
async def autocompletion_json(query: str, limit: int = 10):
    autocompletions = await manticoresearch.autocompletion(query=query, limit=limit)

    return {"autocompletions": autocompletions}


@router.get("/tags", response_model=schemas.NoteTagsResponse)
async def get_note_tags(material_id: UUID):
    tags = await db.get_sorted_tags(material_id=material_id)

    return {"tags": tags}


@router.get("/note-json", response_model=schemas.GetNoteJsonResponse)
async def get_note_json_api(note_id: UUID):
    if note := await cached.get_note_json(note_id):
        return note

    raise HTTPException(status_code=404, detail=f"Note id={note_id} not found")
