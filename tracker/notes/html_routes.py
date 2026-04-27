import asyncio
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import NonNegativeInt

from tracker.common import settings
from tracker.materials import db as materials_db
from tracker.models import enums
from tracker.notes import cached, db, schemas
from tracker.notes.links import get_note_links
from tracker.notes.listing import build_notes_search_result


templates = Jinja2Templates(directory="templates")

# Single-note and update forms are still Jinja (not implemented in React yet).
note_detail_router = APIRouter(tags=["notes-legacy"], deprecated=True)


@note_detail_router.get("/note", response_class=HTMLResponse)
async def get_note(request: Request, note_id: UUID):
    if not (note := await cached.get_note(note_id)):
        raise HTTPException(status_code=404, detail=f"Note id={note_id} not found")

    async with asyncio.TaskGroup() as tg:
        get_material_task = tg.create_task(
            materials_db.get_material(material_id=note.material_id),
        )
        get_note_links_task = tg.create_task(get_note_links(note))

    context = note.model_dump() | {
        "request": request,
        "note_links": get_note_links_task.result(),
        "added_at": note.added_at.strftime(settings.DATETIME_FORMAT),
        "content": note.content_html,
        "note_tags": note.tags_html,
        "link_id": note.link_html,
    }
    if material := get_material_task.result():
        context |= {
            "material_title": material.title,
            "material_authors": material.authors,
            "material_type": material.material_type,
            "material_pages": material.pages,
            "material_is_outlined": material.is_outlined,
        }

    return templates.TemplateResponse(request, "notes/note.html", context)


@note_detail_router.get("/update-view", response_class=HTMLResponse)
async def update_note_view(note_id: UUID, request: Request, success: bool | None = None):  # noqa: FBT001
    context: dict[str, Any] = {
        "request": request,
    }

    if not (note := await cached.get_note(note_id)):
        context["what"] = f"Note id='{note_id}' not found"
        return templates.TemplateResponse(request, "errors/404.html", context)
    material_id = note.get_material_id()

    async with asyncio.TaskGroup() as tg:
        material_type = tg.create_task(db.get_material_type(material_id=material_id))
        get_tags_task = tg.create_task(db.get_sorted_tags(material_id=material_id))
        get_possible_links_task = tg.create_task(db.get_possible_links(note=note))
        get_titles_task = tg.create_task(db.get_material_titles())

    context |= {
        "material_id": material_id,
        "material_type": material_type.result() or enums.MaterialTypesEnum.book.name,
        "note_id": note.note_id,
        "title": note.title or "",
        "content": schemas.demark_note(note.content),
        "link_id": note.link_id,
        "note_tags": note.tags_str,
        "chapter": note.chapter,
        "page": note.page,
        "success": success,
        "tags": get_tags_task.result(),
        "titles": get_titles_task.result(),
    }
    if not note.link_id:
        context["possible_links"] = get_possible_links_task.result()

    return templates.TemplateResponse(request, "notes/update_note.html", context)


router = APIRouter(prefix="/notes", tags=["notes-legacy"])


@router.get("/", response_class=HTMLResponse)
async def get_notes(
    request: Request,
    search: Annotated[schemas.SearchParams, Depends()],
    page: NonNegativeInt = 1,
    page_size: NonNegativeInt = 10,
):
    ctx = await build_notes_search_result(
        search=search,
        page=page,
        page_size=page_size,
    )
    context: dict[str, Any] = {"request": request, **ctx}
    return templates.TemplateResponse(request, "notes/notes.html", context)


@router.get("/add-view", response_class=HTMLResponse)
async def add_note_view(request: Request, material_id: str | None = None):
    material_id = material_id or request.cookies.get("material_id", "")

    async with asyncio.TaskGroup() as tg:
        get_titles_task = tg.create_task(db.get_material_titles())
        get_tags_task = tg.create_task(db.get_sorted_tags(material_id=material_id))

    context = {
        "request": request,
        "material_id": material_id,
        "material_type": request.cookies.get(
            "material_type",
            enums.MaterialTypesEnum.book.name,
        ),
        "content": request.cookies.get("content", ""),
        "page": request.cookies.get("page", ""),
        "chapter": request.cookies.get("chapter", ""),
        "note_id": request.cookies.get("note_id", ""),
        "titles": get_titles_task.result(),
        "tags": get_tags_task.result(),
    }
    return templates.TemplateResponse(request, "notes/add_note.html", context)


@router.get("/graph", response_class=HTMLResponse)
async def get_graph(request: Request, material_id: UUID | str | None = None):
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

    if material_id:
        notes_dict = {note.note_id: note for note in notes}
        material_notes = {note.note_id for note in get_material_notes_task.result()}
        graph = db.create_material_graph(
            material_id=UUID(cast("str", material_id)),
            material_notes=material_notes,
            notes=notes_dict,
        )
    else:
        graph = db.link_all_notes(notes)

    context = {
        "request": request,
        "graph": db.create_graphic(graph, height="80vh"),
        "titles": get_titles_task.result(),
        "material_id": material_id,
    }
    return templates.TemplateResponse(request, "notes/graph.html", context)


router.include_router(note_detail_router)
