import datetime
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tracker.common import models, settings
from tracker.common.log import logger


class DatabaseError(Exception):
    pass


engine = create_async_engine(settings.DB_URI, encoding='utf-8')
engine.sync_engine.run(models.metadata.create_all())


@asynccontextmanager
async def session(**kwargs) -> AsyncGenerator[AsyncSession, None]:
    new_session = AsyncSession(**kwargs, bind=engine, expire_on_commit=False)
    try:
        yield new_session
        await new_session.commit()
    except Exception as e:
        logger.exception("Error with the session: %s")

        await new_session.rollback()
        raise DatabaseError(e)
    finally:
        await new_session.close()


def today() -> datetime.datetime:
    return datetime.datetime.utcnow()


def yesterday() -> datetime.datetime:
    return today() - datetime.timedelta(days=1)


def does_note_exist(note_id: int, /) -> bool:
    logger.info(f"Whether {note_id=} exists")

    with session() as ses:
        return ses.get(Note, note_id) is not None


def get_notes(*,
              materials_ids: Optional[list[int]] = None) -> list[Note]:
    """ Get notes by material ids.
    If it's None, get all notes.
    """
    how_many = 'all'
    if materials_ids:
        how_many = str(len(materials_ids))

    logger.info(f"Getting notes for {how_many} materials")

    with session() as ses:
        query = ses.query(Note)

        if materials_ids:
            query = query\
                .filter(Note.material_id.in_(materials_ids)).all()

        return query.all()


def add_note(*,
             material_id: int,
             content: str,
             chapter: int,
             page: int,
             date: Optional[datetime.date] = None) -> None:
    """ Add note to the database. """
    date = date or today()
    logger.info(f"Adding note for {material_id=} at {date=}")

    with session() as ses:
        note = Note(
            material_id=material_id,
            content=content,
            chapter=chapter,
            page=page,
            date=date
        )

        ses.add(note)
        logger.info("Note added")


def notes_with_cards(*,
                     material_ids: Optional[list[int]] = None) -> set[int]:
    """
    Get notes for which there is a card.

    :return: set if ids of there notes.
    """
    how_many = 'all'
    if material_ids:
        how_many = len(material_ids)
    logger.info(f"Getting notes with a card for {how_many} materials")

    with session() as ses:
        query = ses.query(Note.id)\
            .join(Card, Card.note_id == Note.id)\

        if material_ids:
            query = query\
                .filter(Note.material_id.in_(material_ids))

        return {
            item[0]
            for item in query.all()
        }


def add_card(*,
             material_id: int,
             question: str,
             note_id: int,
             answer: Optional[str] = None) -> None:
    logger.debug("Adding new card")
    today_ = today()

    with session() as ses:
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


def get_cards(*,
              material_ids: Optional[list[int]] = None) -> list[CardNoteRecall]:
    how_many = 'all materials'
    if material_ids:
        how_many = f"material {material_ids=}"

    logger.info(f"Getting cards for {how_many}")

    with session() as ses:
        query = ses.query(Card, Recall, Note)\
            .join(Recall, Card.card_id == Recall.card_id)\
            .join(Note, Card.note_id == Note.id)\
            .filter(Recall.next_repeat_date <= today())

        if material_ids:
            query = query\
                .filter(Card.material_id.in_(material_ids))

    return [
        CardNoteRecall(card=card, note=note, recall=recall)
        for card, recall, note in query.all()
    ]


def all_cards(*,
              material_ids: Optional[list[int]] = None) -> list[CardNoteRecall]:
    how_many = 'all materials'
    if material_ids:
        how_many = f"material {material_ids=}"

    logger.info(f"Getting all cards for {how_many}")

    with session() as ses:
        query = ses.query(Card, Recall, Note) \
            .join(Recall, Card.card_id == Recall.card_id) \
            .join(Note, Card.note_id == Note.id)\

        if material_ids:
            query = query\
                .filter(Card.material_id.in_(material_ids))

    return [
        CardNoteRecall(card=card, note=note, recall=recall)
        for card, recall, note in query.all()
    ]


def complete_card(*,
                  card_id: int,
                  result: str) -> None:
    """
    :exception WrongRepeatResult:
    :exception CardNotFound:
    """
    logger.info(f"Completing card {card_id=} as {result=}")

    with session() as ses:
        card = ses.query(Card, Recall)\
            .join(Card, Card.card_id == Recall.card_id)\
            .filter(Card.card_id == card_id)\
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


def repeated_today(*,
                   material_id: Optional[int] = None) -> int:
    """
    Get count of cards repeated today
    """
    logger.info("Calculating how many cards repeated today")

    with session() as ses:
        query = ses.query(func.count())\
            .select_from(Card, Recall) \
            .join(Recall, Card.card_id == Recall.card_id) \
            .filter(Recall.last_repeat_date == today())\
            .filter(Recall.next_repeat_date != today())

        if material_id:
            query = query.filter(Card.material_id == material_id)

        return query.one()[0]


def remains_for_today(*,
                      material_id: Optional[int] = None) -> int:
    logger.info("Calculating how many cards remains for today")

    with session() as ses:
        query = ses.query(func.count())\
            .select_from(Card, Recall) \
            .join(Recall, Card.card_id == Recall.card_id) \
            .filter(Recall.next_repeat_date <= today())

        if material_id:
            query = query.filter(Card.material_id == material_id)

        return query.one()[0]


def cards_count(*,
                material_ids: Optional[list[int]] = None) -> int:
    how_many = 'all materials'
    if material_ids:
        how_many = f"material {material_ids=}"

    logger.info(f"Getting amount of cards for {how_many}")

    with session() as ses:
        query = ses.query(func.count())\
            .select_from(Card)

        if material_ids:
            query = query\
                .filter(Card.material_id.in_(material_ids))

        return query.one()[0]
