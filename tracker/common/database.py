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


def get_materials(*,
                  materials_ids: Optional[list[int]] = None) -> list[Material]:
    """
    Get the materials by their ids.
    If it's None, get all materials.
    """
    how_many = 'all'
    if materials_ids:
        how_many = str(len(materials_ids))

    logger.info(f"Getting {how_many} materials")

    with session() as ses:
        query = ses.query(Material)

        if materials_ids:
            query = query\
                .filter(Material.material_id.in_(materials_ids))

        return query.all()


def get_material_titles(*,
                        reading: bool = False,
                        completed: bool = False,
                        free: bool = False,
                        all: bool = False) -> dict[int, str]:
    logger.info(f"Getting material titles with: "
                f"{reading=}, {completed=}, {free=}, {all=}")

    with session() as ses:
        query = ses.query(Material.material_id, Material.title)
        res = []

        if all:
            res = query.all()
        else:
            if reading:
                res += query\
                    .join(Status, Status.material_id == Material.material_id)\
                    .filter(Status.end == None)\
                    .all()
            if completed:
                res += query \
                    .join(Status, Status.material_id == Material.material_id) \
                    .filter(Status.end != None) \
                    .all()
            if free:
                free_materials = ses.query(Material, Status)\
                    .join(Status, isauter=True)\
                    .all()
                res += [
                    (material.material_id, material.title)
                    for material, status in free_materials
                    if status is None
                ]

        return {
            material_id: material_title
            for material_id, material_title in res
        }


def get_completion_dates() -> dict[int, datetime.date]:
    logger.info("Getting completion dates")

    with session() as ses:
        res = ses.query(Material.material_id, Status.end)\
            .join(Status, Material.material_id == Status.material_id)\
            .filter(Status.end != None)\
            .all()

    return {
        material_id: completion_date
        for material_id, completion_date in res
    }


def get_title(material_id: int, /) -> str:
    logger.info(f"Getting title for {material_id=}")
    try:
        return get_materials(materials_ids=[material_id])[0].title
    except IndexError:
        logger.warning(f"Material {material_id=} not found")
        return ''


def does_material_exist(material_id: int, /) -> bool:
    logger.info(f"Whether {material_id=} exists")

    with session() as ses:
        return ses.get(Material, material_id) is not None


def does_note_exist(note_id: int, /) -> bool:
    logger.info(f"Whether {note_id=} exists")

    with session() as ses:
        return ses.get(Note, note_id) is not None


def is_material_reading(material_id: int, /) -> bool:
    logger.info(f"Whether {material_id=} reading")

    with session() as ses:
        material = ses.query(Material)\
            .join(Status, Material.material_id == Status.material_id)\
            .filter(Status.begin != None)\
            .filter(Status.end == None)\
            .filter(Material.material_id == material_id)

        return material.first() is not None


def is_material_assigned(material_id: int, /) -> bool:
    logger.info(f"Whether {material_id=} reading or completed")

    with session() as ses:
        material = ses.query(Material) \
            .join(Status, Material.material_id == Status.material_id) \
            .filter(Status.begin != None) \
            .filter(Material.material_id == material_id)

        return material.first() is not None


def get_free_materials() -> list[Material]:
    """ Get all not assigned materials """
    logger.info("Getting free materials")

    with session() as ses:
        return ses.query(Material) \
            .join(Status,
                  Material.material_id == Status.material_id,
                  isouter=True) \
            .where(Status.material_id == None) \
            .all()


def get_reading_materials() -> MATERIAL_STATUS:
    """
    Get all assigned but not completed
    materials and their statuses.
    """
    logger.info("Getting reading materials")

    with session() as ses:
        res = ses.query(Material, Status)\
            .join(Status, Material.material_id == Status.material_id) \
            .filter(Status.end == None) \
            .all()

    return [
        MaterialStatus(material=ms[0], status=ms[1])
        for ms in res
    ]


def get_completed_materials() -> MATERIAL_STATUS:
    """ Get all completed materials and their statuses. """
    logger.info("Getting completed materials")

    with session() as ses:
        res = ses.query(Material, Status)\
            .join(Status, Material.material_id == Status.material_id)\
            .filter(Status.end != None)\
            .all()

    return [
        MaterialStatus(material=ms[0], status=ms[1])
        for ms in res
    ]


def get_status(*,
               status_ids: Optional[list[int]] = None) -> list[Status]:
    """
    Get the statuses by their ids.
    If it's None, get all statuses.
    """
    how_many = 'all'
    if status_ids:
        how_many = str(len(status_ids))

    logger.info(f"Getting {how_many} statuses")

    with session() as ses:
        query = ses.query(Status)

        if status_ids:
            query = query\
                .filter(Status.status_id.in_(status_ids))

        return query.all()


def get_material_status(*,
                        material_id: int) -> Status:
    """ Get material status.

    :exception MaterialNotFound: if the material doesn't exist.
    """
    logger.info(f"Getting status for material {material_id=}")

    with session() as ses:
        material = ses.query(Status) \
            .filter(Status.material_id == material_id) \
            .first()

        if material is None:
            msg = f"Status for material {material_id=} not found"
            logger.error(msg)
            raise ex.MaterialNotFound(msg)
        return material


def add_material(*,
                 title: str,
                 authors: str,
                 pages: int,
                 tags: str) -> None:
    """ Add a material to the database. """
    logger.info(f"Adding material {title=}")

    with session() as ses:
        material = Material(
            title=title,
            authors=authors,
            pages=pages,
            tags=tags
        )
        ses.add(material)

        logger.info(f"Material added, {material.material_id}")


def start_material(*,
                   material_id: int,
                   start_date: Optional[datetime.date] = None) -> None:
    """
    Start a material, add new record to Status table.

    :param material_id: id of material has been started.
    :param start_date: date when the material was started.
     Today by default.

    :exception WrongDate: if 'start_time' is better than today.
    :exception MaterialNotFound: if material with the id not found.
    """
    start_date = start_date or today()
    logger.info(f"Starting material {material_id=} at {start_date=}")

    if start_date > today():
        raise ex.WrongDate("Start date must be less than today,"
                           "but %s found", start_date)

    if not does_material_exist(material_id):
        raise ex.MaterialNotFound(f"Material {material_id=}")

    with session() as ses:
        started_material = Status(
            material_id=material_id, begin=start_date)
        ses.add(started_material)

        logger.info(f"Material {material_id=} started"
                    f"at {start_date=}")


def complete_material(*,
                      material_id: int,
                      completion_date: Optional[datetime.date] = None) -> None:
    """
    Set end date to Status table.

    :param material_id: id of materials to complete.
    :param completion_date: date when the material
     was finished. Today by default.

    :exception MaterialEvenCompleted: if the material has been completed yet.
    :exception WrongDate: if 'completion_date' is less than start date.
    :exception MaterialNotAssigned: if the material has not been started yet.
    """
    completion_date = completion_date or today()
    logger.info(f"Completing material {material_id=} at {completion_date=}")

    with session() as ses:
        status = ses.query(Status)\
            .filter(Status.material_id == material_id)\
            .first()

        if status is None:
            raise ex.MaterialNotAssigned(
                f"Material {material_id=} not assigned")

        if status.end is not None:
            raise ex.MaterialEvenCompleted(f"Material {material_id=}")
        if status.begin > completion_date:
            raise ex.WrongDate("Begin cannot be more than end, but"
                               f"{status.begin=} > {completion_date=}")

        status.end = completion_date
        logger.info(f"Material {material_id=} "
                    f"completed at {completion_date=}")


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
