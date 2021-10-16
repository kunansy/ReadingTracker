from typing import Optional

import sqlalchemy.sql as sa

from tracker.common import database
from tracker.common.log import logger


async def notes_with_cards(*,
                           material_ids: Optional[list[int]] = None) -> set[int]:
    """
    Get notes for which there is a card.

    :return: set if ids of there notes.
    """
    how_many = 'all'
    if material_ids:
        how_many = len(material_ids)
    logger.info(f"Getting notes with a card for {how_many} materials")

    async with database.session() as ses:
        query = ses.query(Note.id) \
            .join(Card, Card.note_id == Note.id)

        if material_ids:
            query = query \
                .filter(Note.material_id.in_(material_ids))

        return {
            item[0]
            for item in query.all()
        }


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


async def complete_card(*,
                        card_id: int,
                        result: str) -> None:
    """
    :exception WrongRepeatResult:
    :exception CardNotFound:
    """
    logger.info(f"Completing card {card_id=} as {result=}")

    async with database.session() as ses:
        card = ses.query(Card, Recall) \
            .join(Card, Card.card_id == Recall.card_id) \
            .filter(Card.card_id == card_id) \
            .first()

        if card is None:
            raise ex.CardNotFound(f"Card {card_id=} not found")

        card, recall = card
        card = CardNoteRecall(card=card, recall=recall)

        if days := card[result]:
            assert days > 0, "Wrong days count"

            recall.last_repeat_date = today()
            recall.next_repeat_date = today() + timedelta(days=days)
        else:
            raise ex.WrongRepeatResult

        recall.mult *= RepeatResults[result].value


async def repeated_today(*,
                         material_id: Optional[int] = None) -> int:
    """
    Get count of cards repeated today
    """
    logger.info("Calculating how many cards repeated today")

    async with database.session() as ses:
        query = ses.query(func.count()) \
            .select_from(Card, Recall) \
            .join(Recall, Card.card_id == Recall.card_id) \
            .filter(Recall.last_repeat_date == today()) \
            .filter(Recall.next_repeat_date != today())

        if material_id:
            query = query.filter(Card.material_id == material_id)

        return query.one()[0]


async def remains_for_today(*,
                            material_id: Optional[int] = None) -> int:
    logger.info("Calculating how many cards remains for today")

    async with database.session() as ses:
        query = ses.query(func.count()) \
            .select_from(Card, Recall) \
            .join(Recall, Card.card_id == Recall.card_id) \
            .filter(Recall.next_repeat_date <= today())

        if material_id:
            query = query.filter(Card.material_id == material_id)

        return query.one()[0]


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
