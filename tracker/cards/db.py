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
                   material_id: int,
                   question: str,
                   note_id: int,
                   answer: Optional[str] = None) -> None:
    logger.debug("Adding new card")
    today_ = database.today()

    async with database.session() as ses:
        card = Card(
            material_id=material_id,
            question=question,
            answer=answer,
            note_id=note_id,
            date=today_
        )
        ses.add(card)

        # commit required to get card_id
        ses.commit()
        logger.info("Card added")

        logger.debug("Starting the card")
        recall = Recall(
            card_id=card.card_id,
            last_repeat_date=today_,
            next_repeat_date=today_
        )
        ses.add(recall)
        logger.debug("Card started")


async def get_cards(*,
                    material_ids: Optional[list[int]] = None) -> list[CardNoteRecall]:
    how_many = 'all materials'
    if material_ids:
        how_many = f"material {material_ids=}"

    logger.info(f"Getting cards for {how_many}")

    async with database.session() as ses:
        query = ses.query(Card, Recall, Note) \
            .join(Recall, Card.card_id == Recall.card_id) \
            .join(Note, Card.note_id == Note.id) \
            .filter(Recall.next_repeat_date <= today())

        if material_ids:
            query = query \
                .filter(Card.material_id.in_(material_ids))

    return [
        CardNoteRecall(card=card, note=note, recall=recall)
        for card, recall, note in query.all()
    ]


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
