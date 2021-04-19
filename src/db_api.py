__all__ = ('get_materials', 'get_status', 'get_completed_materials',
           'get_free_materials', 'complete_material', 'get_title',
           'start_material', 'add_materials', 'get_material_status',
           'get_reading_materials', 'add_note', 'get_notes')

import datetime
import logging
from contextlib import contextmanager
from os import environ
from typing import ContextManager, Callable

from sqlalchemy import Column, ForeignKey, Integer, String, Date, create_engine, \
    Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session


DATE_FORMAT = '%d-%m-%Y'

Base = declarative_base()


class WrongDate(Exception):
    pass


class MaterialEvenCompleted(Exception):
    pass


class MaterialNotAssigned(Exception):
    pass


class MaterialNotFound(Exception):
    pass


class Material(Base):
    __tablename__ = 'material'

    material_id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    authors = Column(String, nullable=False)
    pages = Column(Integer, nullable=False)
    tags = Column(String)

    def __repr__(self) -> str:
        return "Material(" \
               f"{self.material_id}, {self.title}, " \
               f"{self.authors}, {self.pages}, {self.tags})"


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

        return "Status(" \
               f"{self.status_id}, {self.material_id}, " \
               f"{begin}, {end})"


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
               f"{self.id=}, {self.material_id=}, " \
               f"self.{date=}, {self.chapter=}, {self.page=})"


engine = create_engine(environ['DB_URI'], encoding='utf-8')
Base.metadata.create_all(engine)


def cache(func: Callable) -> Callable:
    results = {}

    def wrapped(arg=None):
        nonlocal results

        if arg in results:
            return results[arg]

        if arg is None:
            results[arg] = func()
        else:
            results[arg] = func(arg)

        return results[arg]

    return wrapped


@contextmanager
def session(**kwargs) -> ContextManager[Session]:
    new_session = Session(**kwargs, bind=engine, expire_on_commit=False)
    try:
        yield new_session
        new_session.commit()
    except:
        new_session.rollback()
        raise
    finally:
        new_session.close()


@cache
def today() -> datetime.date:
    return datetime.datetime.now().date()


def get_materials(*,
                  materials_ids: list[int] = None) -> list[Material]:
    """
    Get the materials by their ids or all
    rows of Material table if it is None.

    :param materials_ids: ids of Material row or None.
    :return: list of found Material rows.
    """
    with session() as ses:
        if materials_ids is None:
            return ses.query(Material).all()

        return ses.query(Material).filter(
            Material.material_id.in_(materials_ids)).all()


@cache
def get_title(material_id: int) -> str:
    try:
        return get_materials(materials_ids=[material_id])[0].title
    except IndexError:
        logging.error(f"Material {material_id=} not found")
        return ''


def get_free_materials() -> list[Material]:
    """ Get all not assigned materials """
    assigned_materials_ids = {
        status.material_id
        for status in get_status()
    }

    return [
        material
        for material in get_materials()
        if material.material_id not in assigned_materials_ids
    ]


def get_reading_materials() -> list[tuple[Material, Status]]:
    """ Get all materials read now. """
    status = get_status()

    reading_materials_ids = [
        status_.material_id
        for status_ in status
        if status_.end is None
    ]
    status = {
        status_.material_id: status_
        for status_ in status
        if status_.material_id in reading_materials_ids
    }
    materials = get_materials(materials_ids=reading_materials_ids)

    return [
        (material, status[material.material_id])
        for material in materials
    ]


def get_completed_materials() -> list[Material]:
    """ Get all completed materials. """
    with session() as ses:
        return ses.query(Material).join(Status)\
                  .filter(Status.end != None).all()


def get_status(*,
               status_ids: list[int] = None) -> list[Status]:
    """
    Get the status by their ids or all
    rows of Status table if it is None.

    :param status_ids: ids of Status row or None.
    :return: list of found Status rows.
    """
    with session() as ses:
        if status_ids is None:
            return ses.query(Status).all()

        return ses.query(Status).filter(
            Status.status_id.in_(status_ids)).all()


def get_material_status(*,
                        material_id: int) -> Status:
    with session() as ses:
        return ses.query(Status).filter(
            Status.material_id == material_id).one()


def add_materials(materials: list[dict]) -> None:
    """
    Add some materials to the table.

    :param materials: list of dicts with all
    required for class Material params.
    """
    with session() as ses:
        for material in materials:
            material = Material(**material)
            ses.add(material)


def start_material(*,
                   material_id: int,
                   start_date: datetime.date = None) -> None:
    """
    Start a material, add new record to Status table.

    :param material_id: id of material has been started.
    :param start_date: date when the material was started.
     Today by default.

    :exception WrongDate: if 'start_time' is better than today.
    """
    with session() as ses:
        start_date = start_date or today()

        if start_date > today():
            raise WrongDate("Start date must be less than today,"
                            "but %s found", start_date)

        started_material = Status(
            material_id=material_id, begin=start_date)
        ses.add(started_material)


def complete_material(*,
                      material_id: int,
                      completion_date: datetime.date = None) -> None:
    """
    Set end date to Status table by 'material_id'.

    :param material_id: id of materials to complete.
    :param completion_date: date when the material
     was finished. Today by default.

    :exception MaterialEvenCompleted: if the material has been completed yet.
    :exception WrongDate: if 'completion_date' is less than start date.
    :exception MaterialNotAssigned: if the material has not been started yet.
    """
    with session() as ses:
        completion_date = completion_date or today()

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


def get_notes(*,
              materials_ids: list[int] = None) -> list[Note]:
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
    with session() as ses:
        date = date or today()

        note = Note(
            material_id=material_id,
            content=content,
            chapter=chapter,
            page=page,
            date=date
        )

        ses.add(note)
