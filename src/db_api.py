__all__ = ('get_materials', 'get_status', 'get_completed_materials',
           'get_free_materials', 'complete_material', 'get_title',
           'start_material', 'add_materials')

import datetime
import logging
from contextlib import contextmanager
from os import environ
from typing import ContextManager, Callable

from sqlalchemy import Column, ForeignKey, Integer, String, Date, create_engine, \
    MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session


DATE_FORMAT = '%d-%m-%Y'

Base = declarative_base()


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


metadata = MetaData()

engine = create_engine(environ['DB_URI'], encoding='utf-8')
Base.metadata.create_all(engine)

conn = engine.connect()


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
    """ Get all not completed materials """
    all_materials = get_materials()
    completed_materials = {
        status.material_id
        for status in get_status()
        if status.end is not None
    }

    return [
        material
        for material in all_materials
        if material.material_id not in completed_materials
    ]


def get_completed_materials() -> list[Material]:
    """
    Get all completed materials.

    :return: list of Materials where 'end' is not None.
    """
    with session() as ses:
        return ses.query(Material).join(Status).filter(Status.end != None)


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

    :exception ValueError: if 'start_time' is better than today.
    """
    with session() as ses:
        start_date = start_date or today()

        if start_date > today():
            raise ValueError("Start date mus be less than today,"
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

    :exception ValueError: if the material has been completed
     yet or if 'completion_date' is less than start date.
    :exception IndexError: if the material has not been started yet.
    """
    with session() as ses:
        completion_date = completion_date or today()

        status = ses.query(Status).filter(
            Status.material_id == material_id).all()[0]

        if status.end is not None:
            raise ValueError(f"Material {material_id=} even completed")
        if status.begin > completion_date:
            raise ValueError("Begin cannot be more than end, but"
                             f"{status.begin=} > {completion_date=}")

        status.end = completion_date
