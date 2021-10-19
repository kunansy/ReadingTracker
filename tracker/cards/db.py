from typing import Any, Optional
from uuid import UUID

import sqlalchemy.sql as sa

from tracker.common import database, models
from tracker.common.log import logger


async def notes_with_cards(*,
                           material_ids: Optional[list[UUID]] = None) -> set[UUID]:
    how_many = 'all'
    if material_ids:
        how_many = str(len(material_ids))
    logger.info(f"Getting notes with a card for {how_many} materials")

    stmt = sa.select(models.Notes.c.note_id)\
        .join(models.Cards,
              models.Cards.c.note_id == models.Cards.c.note_id)
    if material_ids:
        stmt = stmt \
            .where(models.Notes.c.material_id.in_(material_ids))

    async with database.session() as ses:
        return (await ses.execute(stmt)).all()


async def get_material_titles() -> dict[UUID, str]:
    return await database.get_material_titles()


async def add_card(*,
                   material_id: UUID,
                   note_id: UUID,
                   question: str,
                   answer: Optional[str] = None) -> None:
    logger.debug("Adding new card")

    values = {
        "material_id": material_id,
        "note_id": note_id,
        "question": question,
        "answer": answer,
    }
    stmt = models.Cards\
        .insert().values(values)
    async with database.session() as ses:
        await ses.execute(stmt)
    logger.debug("Card added")


async def all_cards(*,
                    material_ids: Optional[list[int]] = None) -> list[dict[str, Any]]:
    how_many = 'all materials'
    if material_ids:
        how_many = f"material {material_ids=}"

    logger.info(f"Getting all cards for {how_many}")

    stmt = sa.select([models.Cards, models.Notes]) \
        .join(models.Notes,
              models.Cards.c.note_id == models.Notes.c.id)

    if material_ids:
        stmt = stmt \
            .where(models.Cards.c.material_id.in_(material_ids))

    async with database.session() as ses:
        return [
            {"card": card, "note": note}
            async for card, note in await ses.stream(stmt)
        ]


async def cards_count(*,
                      material_ids: Optional[list[int]] = None) -> int:
    how_many = 'all materials'
    if material_ids:
        how_many = f"material {material_ids=}"

    logger.debug(f"Getting amount of cards for {how_many}")

    stmt = sa.select(sa.func.count(1))\
        .select_from(models.Cards)
    if material_ids:
        stmt = stmt.where(models.Cards.c.material_id.in_(material_ids))

    async with database.session() as ses:
        return await ses.scalar(stmt)
