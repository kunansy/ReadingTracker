from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from tracker.common import kafka, manticoresearch
from tracker.common.logger import logger
from tracker.notes import cached, db, schemas


router = APIRouter(prefix="/notes", tags=["notes"])


@router.get("/note-json", response_model=schemas.GetNoteJsonResponse)
async def get_note_json(note_id: UUID):
    if note := await cached.get_note_json(note_id):
        return note

    raise HTTPException(status_code=404, detail=f"Note id={note_id} not found")


@router.get("/material-notes", response_model=schemas.GetMaterialNotes)
async def get_material_notes_json(material_id: UUID):
    notes = await db.get_notes(material_id=material_id)

    return {
        "material_id": material_id,
        "notes": notes,
    }


@router.post("/add", response_class=RedirectResponse)
async def add_note(note: Annotated[schemas.Note, Form()]):
    redirect_url = "/notes/add-view"
    response = RedirectResponse(redirect_url, status_code=302)

    for key, value in note.model_dump(
        exclude={"content", "tags", "link_id", "title"},
        exclude_none=True,
    ).items():
        response.set_cookie(key, value, expires=3600)

    note_id = await db.add_note(
        material_id=note.material_id,
        link_id=note.link_id,
        title=note.title,
        content=note.content,
        chapter=note.chapter,
        page=note.page,
        tags=note.tags,
    )

    response.set_cookie("note_id", note_id, expires=5)
    if material_type := await db.get_material_type(material_id=note.material_id):
        response.set_cookie("material_type", material_type, expires=5)

    return response


@router.post("/update", response_class=RedirectResponse)
async def update_note(note: Annotated[schemas.UpdateNote, Form()]):
    success = True

    try:
        await db.update_note(
            note_id=note.note_id,
            material_id=note.get_material_id(),
            link_id=note.link_id,
            title=note.title,
            content=note.content,
            chapter=note.chapter,
            page=note.page,
            tags=note.tags,
        )

    except Exception as e:
        logger.error("Error updating note: %s", repr(e))
        success = False

    redirect_url = f"/notes/update-view?note_id={note.note_id}&success={success}"

    return RedirectResponse(redirect_url, status_code=302)


@router.get("/is-deleted", response_model=schemas.IsNoteDeletedResponse)
async def is_note_deleted(note_id: UUID):
    result = await cached.is_deleted(note_id)

    return {"is_deleted": result, "note_id": note_id}


@router.delete("/delete", status_code=201)
async def delete_note(note_id: Annotated[UUID, Body(embed=True)]):
    await db.delete_note(note_id=note_id)


@router.post("/restore", status_code=201)
async def restore_note(note_id: Annotated[UUID, Body(embed=True)]):
    await db.restore_note(note_id=note_id)


@router.get("/links", response_class=HTMLResponse)
async def get_note_graph(note_id: UUID):
    notes = {note.note_id: note for note in await db.get_notes()}
    graph = db.link_notes(note_id=note_id, notes=notes)
    return db.create_graphic(graph)


@router.get("/tags")
async def get_tags(material_id: UUID):
    tags = await db.get_sorted_tags(material_id=material_id)

    return {"tags": tags}


@router.post("/repeat-queue/insert")
async def insert_to_repeat_queue(note_id: UUID):
    if await cached.get_note(note_id):
        await kafka.repeat_note(note_id)
    else:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/autocompletion", response_model=schemas.AutocompletionResponse)
async def autocompletion(query: str, limit: int = 10):
    autocompletions = await manticoresearch.autocompletion(query=query, limit=limit)

    return {"autocompletions": autocompletions}
