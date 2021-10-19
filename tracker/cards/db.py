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
                    material_ids: Optional[list[int]] = None) -> list[CardNoteRecall]:
    how_many = 'all materials'
    if material_ids:
        how_many = f"material {material_ids=}"

    logger.info(f"Getting all cards for {how_many}")

    async with database.session() as ses:
        query = ses.query(Card, Recall, Note) \
            .join(Recall, Card.card_id == Recall.card_id) \
            .join(Note, Card.note_id == Note.id)

        if material_ids:
            query = query \
                .filter(Card.material_id.in_(material_ids))

    return [
        CardNoteRecall(card=card, note=note, recall=recall)
        for card, recall, note in query.all()
    ]


async def cards_count(*,
                      material_ids: Optional[list[int]] = None) -> int:
    how_many = 'all materials'
    if material_ids:
        how_many = f"material {material_ids=}"

    logger.info(f"Getting amount of cards for {how_many}")

    async with database.session() as ses:
        query = ses.query(sa.func.count()) \
            .select_from(Card)

        if material_ids:
            query = query \
                .filter(Card.material_id.in_(material_ids))

        return query.one()[0]
