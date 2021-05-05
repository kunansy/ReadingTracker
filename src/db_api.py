__all__ = ('get_materials', 'get_status', 'get_completed_materials',
           'get_free_materials', 'complete_material', 'get_title',
           'start_material', 'add_material', 'get_material_status',
           'get_reading_materials', 'add_note', 'get_notes',
           'BaseDBError', 'WrongDate', 'MaterialEvenCompleted',
           'MaterialNotAssigned', 'MaterialNotFound', 'MATERIAL_STATUS')

import datetime
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from os import environ
from typing import ContextManager, Callable

from sqlalchemy import (
    Column, ForeignKey, Integer,
    String, Date, create_engine, Text
)
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session


DATE_FORMAT = '%d-%m-%Y'

Base = declarative_base()
logger = logging.getLogger('ReadingTracker')


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


MATERIAL_STATUS = list[MaterialStatus]
engine = create_engine(environ['DB_URI'], encoding='utf-8')
Base.metadata.create_all(engine)


def cache(func: Callable) -> Callable:
    results = {}

    def wrapped(arg=None):
        nonlocal results

        if arg in results:
            logger.debug(f"Result for {func.__name__}({arg})='{results[arg]}' "
                         "got from cache")
            return results[arg]

        if arg is None:
            results[arg] = func()
        else:
            results[arg] = func(arg)

        logger.debug(f"Result for {func.__name__}({arg}) calculated and "
                     f"put into cache"
        )

        return results[arg]

    return wrapped


@contextmanager
def session(**kwargs) -> ContextManager[Session]:
    new_session = Session(**kwargs, bind=engine, expire_on_commit=False)
    try:
        logger.info("New session created and yielded")
        yield new_session

        logger.info("Operations with the session finished, commiting")
        new_session.commit()
    except Exception as e:
        logger.error(f"Error with the session: {e}")
        logger.info("Rollback all changes")

        new_session.rollback()
        raise BaseDBError(e)
    finally:
        new_session.close()
        logger.info("Session closed")


@cache
def today() -> datetime.date:
    return datetime.datetime.now().date()


def get_materials(*,
                  materials_ids: list[int] = None) -> list[Material]:
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


@cache
def get_title(material_id: int, /) -> str:
    logger.info(f"Getting title for {material_id=}")
    try:
        return get_materials(materials_ids=[material_id])[0].title
    except IndexError:
        logger.warning(f"Material {material_id=} not found")
        return ''


@cache
def does_material_exist(material_id: int, /) -> bool:
    logger.info(f"Whether {material_id=} exists")
    return len(get_materials(materials_ids=[material_id])) == 1


def get_free_materials() -> list[Material]:
    """ Get all not assigned materials """
    logger.info("Getting free materials")

    assigned_materials_ids = {
        status.material_id
        for status in get_status()
    }

    return [
        material
        for material in get_materials()
        if material.material_id not in assigned_materials_ids
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
               status_ids: list[int] = None) -> list[Status]:
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
                   start_date: datetime.date = None) -> None:
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

    with session() as ses:
        if start_date > today():
            raise WrongDate("Start date must be less than today,"
                            "but %s found", start_date)

        if not does_material_exist(material_id=material_id):
            raise MaterialNotFound(f"Material {material_id=}")

        started_material = Status(
            material_id=material_id, begin=start_date)
        ses.add(started_material)

        logger.info(f"Material {material_id=} started"
                    f"at {start_date=}")


def complete_material(*,
                      material_id: int,
                      completion_date: datetime.date = None) -> None:
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
              materials_ids: list[int] = None) -> list[Note]:
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
             date: datetime.date = None) -> None:
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
