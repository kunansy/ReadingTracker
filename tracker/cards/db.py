import datetime
from typing import cast
from uuid import UUID

import sqlalchemy.sql as sa

from tracker.common import database
from tracker.common.logger import logger
from tracker.common.schemas import CustomBaseModel
from tracker.models import enums, models
from tracker.notes import db as notes_db


class Card(CustomBaseModel):
    card_id: UUID
    note_id: UUID
    material_id: UUID
    question: str
    answer: str | None
    added_at: datetime.datetime
    note_title: str | None
    note_content: str
    note_chapter: str
    note_page: int
    material_title: str
    material_authors: str
    material_type: enums.MaterialTypesEnum


async def get_notes_with_cards() -> set[UUID]:
    logger.info("Getting notes with cards")

    stmt = sa.select(models.Cards.c.note_id.distinct())

    async with database.session() as ses:
        note_ids = await ses.scalars(stmt)

    return set(note_ids)


async def add_card(
    *,
    material_id: UUID,
    note_id: UUID,
    question: str,
    answer: str | None = None,
) -> UUID:
    logger.debug("Adding new card")

    values = {
        "material_id": str(material_id),
        "note_id": str(note_id),
        "question": question,
        "answer": answer,
    }
    stmt = models.Cards.insert().values(values).returning(models.Cards.c.card_id)

    async with database.session() as ses:
        card_id = await ses.execute(stmt)

    logger.debug("Card %r added", card_id)
    return cast("UUID", card_id)


async def get_cards(
    *,
    note_id: UUID | None = None,
    material_id: UUID | str | None = None,
) -> list[Card]:
    logger.info("Getting all cards")

    stmt = (
        sa.select(
            models.Cards,
            models.Notes.c.title.label("note_title"),
            models.Notes.c.content.label("note_content"),
            models.Notes.c.chapter.label("note_chapter"),
            models.Notes.c.page.label("note_page"),
            models.Materials.c.authors.label("material_authors"),
            models.Materials.c.material_type,
            models.Materials.c.title.label("material_title"),
        )
        .join(models.Notes, models.Cards.c.note_id == models.Notes.c.note_id)
        .join(
            models.Materials,
            models.Notes.c.material_id == models.Materials.c.material_id,
        )
        .order_by(models.Notes.c.note_number)
    )
    if note_id:
        stmt = stmt.where(models.Cards.c.note_id == str(note_id))
    if material_id:
        stmt = stmt.where(models.Cards.c.material_id == str(material_id))

    async with database.session() as ses:
        return [
            Card.model_validate(row, from_attributes=True)
            for row in (await ses.execute(stmt)).all()
        ]


async def get_all_cards_count() -> dict[UUID, int]:
    stmt = sa.select(
        models.Cards.c.material_id.label("material"),
        sa.func.count(1).label("cnt"),
    ).group_by(models.Cards.c.material_id)

    async with database.session() as ses:
        return {row.material: row.cnt for row in (await ses.execute(stmt)).all()}


async def get_cards_count(
    *,
    note_id: UUID | None = None,
    material_id: UUID | None = None,
) -> int:
    logger.debug("Getting amount of cards")

    stmt = sa.select(sa.func.count(1)).select_from(models.Cards)
    if note_id:
        stmt = stmt.where(models.Cards.c.note_id == str(note_id))
    if material_id:
        stmt = stmt.where(models.Cards.c.material_id == str(material_id))

    async with database.session() as ses:
        return await ses.scalar(stmt) or 0


get_material_titles = notes_db.get_material_titles
get_notes = notes_db.get_notes
