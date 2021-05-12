import datetime
import logging
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import ContextManager, Callable, Optional

from environs import Env
from sqlalchemy import (
    Column, ForeignKey, Integer,
    String, Date, create_engine, Text, Float, func
)
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session


env = Env()
DATE_FORMAT = '%d-%m-%Y'

Base = declarative_base()
logger = logging.getLogger(env('LOGGER_NAME'))


class BaseDBError(Exception):
    pass


class WrongDate(BaseDBError):
    pass


class MaterialEvenCompleted(BaseDBError):
    pass


class MaterialNotAssigned(BaseDBError):
    pass


class MaterialNotFound(BaseDBError):
    pass


class WrongRepeatResult(BaseDBError):
    pass


class CardNotFound(BaseDBError):
    pass


class Material(Base):
    __tablename__ = 'material'

    material_id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    authors = Column(String, nullable=False)
    pages = Column(Integer, nullable=False)
    tags = Column(String)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(" \
               f"id={self.material_id}, title={self.title}, " \
               f"authors={self.authors}, pages={self.pages}, " \
               f"tags={self.tags})"

    def __str__(self) -> str:
        return f"ID: {self.material_id}\n" \
               f"Title: «{self.title}»\n" \
               f"Authors: {self.authors}\n" \
               f"Pages: {self.pages}\n" \
               f"Tags: {self.tags}"


class Status(Base):
    __tablename__ = 'status'

    status_id = Column(Integer, primary_key=True)
    material_id = Column(Integer,
                         ForeignKey('material.material_id'),
                         nullable=False,
                         unique=True)
    begin = Column(Date)
    end = Column(Date)

    def __repr__(self) -> str:
        if begin := self.begin:
            begin = begin.strftime(DATE_FORMAT)
        if end := self.end:
            end = end.strftime(DATE_FORMAT)

        return f"{self.__class__.__name__}(" \
               f"id={self.status_id}, material_id={self.material_id}, " \
               f"{begin=}, {end=})"


class Note(Base):
    __tablename__ = 'note'

    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    material_id = Column(Integer,
                         ForeignKey('material.material_id'),
                         nullable=False)
    date = Column(Date, nullable=False)
    chapter = Column(Integer, nullable=False)
    page = Column(Integer, nullable=False)

    def __repr__(self) -> str:
        date = self.date.strftime(DATE_FORMAT)

        return f"{self.__class__.__name__}(" \
               f"id={self.id}, content={self.content}, " \
               f"material_id={self.material_id}, " \
               f"{date=}, chapter={self.chapter}, page={self.page})"


@dataclass
class MaterialStatus:
    material: Material
    status: Status

    def __init__(self,
                 material: Material,
                 status: Status) -> None:
        assert material.material_id == status.material_id

        self.material = material
        self.status = status

    def __setattr__(self,
                    key: str,
                    value) -> None:
        if getattr(self, key, None) is not None:
            raise NotImplementedError(
                f"You can't change {self.__class__.__name__} values, but "
                f"{key}={value} found, when {key}={getattr(self, key)}"
            )

        super().__setattr__(key, value)


class Card(Base):
    __tablename__ = 'card'

    card_id = Column(Integer, primary_key=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True, default=None)
    date = Column(Date, nullable=False)
    material_id = Column(Integer,
                         ForeignKey('material.material_id'),
                         nullable=False)
    note_id = Column(Integer,
                     ForeignKey('note.id'),
                     nullable=False)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(" \
               f"card_id={self.card_id}, question={self.question}, " \
               f"answer={self.answer}, date={self.date}, " \
               f"material_id={self.material_id}, note_id={self.note_id})"


class Recall(Base):
    __tablename__ = 'recall'

    recall_id = Column(Integer, primary_key=True)
    card_id = Column(Integer,
                     ForeignKey('card.card_id'),
                     nullable=False)
    last_repeat_date = Column(Date, nullable=False)
    next_repeat_date = Column(Date, nullable=False)
    mult = Column(Float, nullable=False, default=1.)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(" \
               f"recall_id={self.recall_id}, card_id={self.card_id}, " \
               f"last_repeat_date={self.last_repeat_date}, " \
               f"next_repeat_date={self.next_repeat_date}, mult={self.mult}"


@dataclass
class CardNoteRecall:
    card: Card
    recall: Recall
    note: Optional[Note] = None

    def __init__(self,
                 card: Card,
                 recall: Recall,
                 note: Optional[Note] = None) -> None:
        assert card.card_id == recall.card_id

        self.card = card
        self.recall = recall
        self.note = note

    @property
    def old_duration(self) -> int:
        return (self.recall.next_repeat_date -
                self.recall.last_repeat_date).days or 2

    @property
    def bad(self) -> int:
        return round(
            self.old_duration * self.recall.mult *
            RepeatResults['bad'].value
        )

    @property
    def good(self) -> int:
        return round(
            self.old_duration * self.recall.mult *
            RepeatResults['good'].value
        )

    @property
    def excellent(self) -> int:
        return round(
            self.old_duration * self.recall.mult *
            RepeatResults['excellent'].value
        )

    @property
    def tomorrow(self) -> int:
        return 1

    @property
    def d10(self) -> int:
        return 10

    def __getitem__(self,
                    item: str) -> int:
        try:
            return getattr(super(), item)
        except AttributeError:
            return getattr(self, item, None)

    def __setattr__(self,
                    key: str,
                    value) -> None:
        if getattr(self, key, None) is not None:
            raise NotImplementedError(
                f"You can't change {self.__class__.__name__} values, but "
                f"{key}={value} found, when {key}={getattr(self, key)}"
            )

        super().__setattr__(key, value)


class RepeatResults(Enum):
    tomorrow = .75
    d10 = 2.5
    bad = 1
    good = 1.5
    excellent = 2


MATERIAL_STATUS = list[MaterialStatus]
engine = create_engine(env('DB_URI'), encoding='utf-8')
Base.metadata.create_all(engine)


def cache(*,
          update: bool,
          times: int = 10) -> Callable:
    def decorator(func: Callable) -> Callable:
        results = {}
        call_st = defaultdict(int)
        fname = func.__name__

        def wrapped(*args, **kwargs):
            nonlocal results, call_st

            assert not kwargs, "Kwargs not supported here"

            arg_id = hash(args)
            call_st[arg_id] += 1

            if results.get(arg_id) is None:
                logger.debug(f"{fname}{args} called first time, "
                             "calculating the result")

                results[arg_id] = func(*args)
                return results[arg_id]

            called_numbers = call_st[arg_id]
            if (update and called_numbers >= times and
                    not called_numbers % times):
                logger.debug(
                    f"{fname}{args} called "
                    f"{called_numbers} times, updating the value"
                )

                if (new_res := func(*args)) == results[arg_id]:
                    logger.debug('New result == to the last one')
                else:
                    logger.debug('New result != to the last one')

                results[arg_id] = new_res
            else:
                res = str(results[arg_id])
                shorted_res = res[:5] + '...' + res[-5:]
                logger.debug(f"{fname}{args}='{shorted_res}' "
                             "got from cache")

            return results[arg_id]
        return wrapped
    return decorator


@contextmanager
def session(**kwargs) -> ContextManager[Session]:
    new_session = Session(**kwargs, bind=engine, expire_on_commit=False)
    try:
        logger.debug("New session created and yielded")
        yield new_session

        logger.debug("Operations with the session finished, committing")
        new_session.commit()
    except Exception as e:
        logger.error(f"Error with the session: {e}")
        logger.debug("Rollback all changes")

        new_session.rollback()

        if isinstance(e, BaseDBError):
            raise e
        raise BaseDBError(e)
    finally:
        new_session.close()
        logger.debug("Session closed")


@cache(update=False)
def today() -> datetime.date:
    return datetime.datetime.now().date()


def get_materials(*,
                  materials_ids: Optional[list[int]] = None) -> list[Material]:
    """
    Get the materials by their ids.
    If it's None, get all materials.
    """
    how_many = 'all'
    if materials_ids is not None:
        how_many = str(len(materials_ids))

    logger.info(f"Getting {how_many} materials")

    with session() as ses:
        if materials_ids is None:
            return ses.query(Material).all()

        return ses.query(Material).filter(
            Material.material_id.in_(materials_ids)).all()


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


def get_title(material_id: int, /) -> str:
    logger.info(f"Getting title for {material_id=}")
    try:
        return get_materials(materials_ids=[material_id])[0].title
    except IndexError:
        logger.warning(f"Material {material_id=} not found")
        return ''


def does_material_exist(material_id: int, /) -> bool:
    logger.info(f"Whether {material_id=} exists")
    return len(get_materials(materials_ids=[material_id])) == 1


def get_free_materials() -> list[Material]:
    """ Get all not assigned materials """
    logger.info("Getting free materials")

    with session() as ses:
        res = ses.query(Status, Material) \
            .join(Status, isouter=True) \
            .all()

    return [
        material
        for status, material in res
        if status is None
    ]


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
    if status_ids is not None:
        how_many = str(len(status_ids))

    logger.info(f"Getting {how_many} statuses")

    with session() as ses:
        if status_ids is None:
            return ses.query(Status).all()

        return ses.query(Status).filter(
            Status.status_id.in_(status_ids)).all()


def get_material_status(*,
                        material_id: int) -> Status:
    """ Get material status.

    :exception MaterialNotFound: if the material doesn't exist.
    """
    logger.info(f"Getting status for material {material_id=}")

    with session() as ses:
        query = ses.query(Status).filter(
            Status.material_id == material_id)
        try:
            return query.one()
        except NoResultFound as e:
            msg = f"Material {material_id=} not found"
            logger.error(f"{msg}\n{e}")
            raise MaterialNotFound(msg)


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
        raise WrongDate("Start date must be less than today,"
                        "but %s found", start_date)

    if not does_material_exist(material_id):
        raise MaterialNotFound(f"Material {material_id=}")

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
        status = ses.query(Status).filter(
            Status.material_id == material_id).all()
        try:
            status = status[0]
        except IndexError:
            raise MaterialNotAssigned(f"Material {material_id=} not assigned")

        if status.end is not None:
            raise MaterialEvenCompleted(f"Material {material_id=}")
        if status.begin > completion_date:
            raise WrongDate("Begin cannot be more than end, but"
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
    if materials_ids is not None:
        how_many = str(len(materials_ids))

    logger.info(f"Getting notes for {how_many} materials")

    with session() as ses:
        if materials_ids:
            return ses.query(Note).filter(
                Note.material_id.in_(materials_ids)).all()

        return ses.query(Note).all()


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
              material_id: Optional[int] = None) -> list[CardNoteRecall]:
    how_many = 'all materials'
    if material_id is not None:
        how_many = f"material {material_id=}"

    logger.info(f"Getting cards for {how_many}")

    with session() as ses:
        query = ses.query(Card, Recall, Note)\
            .join(Recall, Card.card_id == Recall.card_id)\
            .join(Note, Card.note_id == Note.id)\
            .filter(Recall.next_repeat_date <= today())

        if material_id:
            query = query.filter(Card.material_id == material_id)

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
        res = ses.query(Card, Recall)\
            .join(Card, Card.card_id == Recall.card_id)\
            .filter(Card.card_id == card_id)\
            .all()

        if not res:
            raise CardNotFound(f"Card {card_id=} not found")

        card_, recall = res[0]
        card = CardNoteRecall(card=card_, recall=recall)

        recall.last_repeat_date = today()

        if days := card[result]:
            recall.next_repeat_date = today() + timedelta(days=days)
        else:
            raise WrongRepeatResult

        coeff = RepeatResults[result].value
        recall.mult *= coeff


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
        query = ses.query(Card, Recall) \
            .join(Recall, Card.card_id == Recall.card_id) \
            .filter(Recall.next_repeat_date == today())

        if material_id:
            query = query.filter(Card.material_id == material_id)

        # TODO: somehow use func.count() instead
        return len(query.all())
