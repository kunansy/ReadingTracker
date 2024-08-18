import asyncio
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from tracker.cards import db, schemas
from tracker.common import settings


router = APIRouter(prefix="/cards", tags=["cards"])
templates = Jinja2Templates(directory="templates")


@router.get("/list", response_class=HTMLResponse)
async def list_cards(
    request: Request,
    note_id: UUID | None = None,
    material_id: UUID | None = None,
):
    async with asyncio.TaskGroup() as tg:
        cards_list_task = tg.create_task(
            db.get_cards_list(note_id=note_id, material_id=material_id),
        )
        total_cards_count_task = tg.create_task(db.get_cards_count())

    # TODO: menu with materials and titles
    context = {
        "request": request,
        "cards": cards_list_task.result(),
        "DATE_FORMAT": settings.DATE_FORMAT,
        "total": total_cards_count_task.result(),
    }
    return templates.TemplateResponse("cards/cards_list.html", context)


@router.get("/has-cards", response_model=schemas.GetHasCards)
async def has_cards(note_id: UUID):
    cards_count = await db.get_cards_count(note_id=note_id)

    return {
        "note_id": note_id,
        "has_cards": cards_count >= 1,
        "cards_count": cards_count,
    }


@router.get("/add-view", response_class=HTMLResponse)
async def add_card_view(
    request: Request,
    material_id: UUID | None = None,
    note_id: UUID | None = None,
):
    material_id = material_id or request.cookies.get("material_id") or ""  # type: ignore[assignment]

    async with asyncio.TaskGroup() as tg:
        notes_task = tg.create_task(db.get_notes(material_id=material_id))
        titles_task = tg.create_task(db.get_material_titles())

    notes = {note.note_id: note for note in notes_task.result()}

    context: dict[str, Any] = {
        "request": request,
        "material_id": material_id,
        "note_id": note_id or request.cookies.get("note_id", ""),
        "question": request.cookies.get("question", ""),
        "answer": request.cookies.get("answer", ""),
        "chapter": request.cookies.get("chapter", ""),
        "titles": titles_task.result(),
        "notes": notes,
        "notes_with_cards": [],
    }
    return templates.TemplateResponse("cards/add_card.html", context)


@router.post("/add")
async def add_card(card: schemas.Card = Depends()):
    await db.add_card(
        material_id=card.material_id,
        note_id=card.note_id,
        question=card.question,
        answer=card.answer,
    )

    url = router.url_path_for(add_card_view.__name__)
    response = RedirectResponse(f"{url}?material_id={card.material_id}", status_code=302)

    for key, value in card.model_dump(
        exclude={"question", "note_id"},
        exclude_none=True,
    ).items():
        response.set_cookie(key, value, expires=60)

    return response
