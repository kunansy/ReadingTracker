import datetime
from uuid import UUID

import sqlalchemy.sql as sa

from tracker.common import database
from tracker.common.logger import logger
from tracker.common.schemas import CustomBaseModel
from tracker.models import enums, models


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


async def notes_with_cards() -> list[UUID]:
    logger.info("Getting notes with a card")

    stmt = sa.select(models.Notes.c.note_id).join(
        models.Cards,
        models.Cards.c.note_id == models.Notes.c.note_id,
    )

    async with database.session() as ses:
        return await ses.scalars(stmt)  # type: ignore[return-value]


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
    return card_id  # type: ignore[return-value]


async def get_cards_list() -> list[Card]:
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
        .order_by(models.Cards.c.added_at.desc())
    )

    async with database.session() as ses:
        return [Card(**row) for row in (await ses.execute(stmt)).mappings().all()]


async def get_cards_count() -> int:
    logger.debug("Getting amount of cards")

    stmt = sa.select(sa.func.count(1)).select_from(models.Cards)  # type: ignore[arg-type]

    async with database.session() as ses:
        return await ses.scalar(stmt) or 0
