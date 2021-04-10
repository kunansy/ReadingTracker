__all__ = ('get_materials', 'get_status', 'get_completed_materials',
           'get_free_materials', 'complete_material')

from contextlib import contextmanager
from os import environ
from typing import ContextManager

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
    size = Column(Integer, nullable=False,
                  doc="Amount of pages, count of lectures etc.")
    tags = Column(String)

    def __repr__(self) -> str:
        return "Material(" \
               f"{self.material_id}, {self.title}, " \
               f"{self.authors}, {self.size}, {self.tags})"


class Status(Base):
    __tablename__ = 'status'

    status_id = Column(Integer, primary_key=True)
    material_id = Column(Integer,
                         ForeignKey('material.material_id'),
                         nullable=False)
    begin = Column(Date)
    end = Column(Date)

    def __repr__(self) -> str:
        material_title = ...

        if begin := self.begin:
            begin = begin.strftime(DATE_FORMAT)
        if end := self.end:
            end = end.strftime(DATE_FORMAT)

        return "Status(" \
               f"{self.status_id}, {material_title}, " \
               f"{begin}, {end})"


metadata = MetaData()

engine = create_engine(environ['DB_URI'], echo=True)
Base.metadata.create_all(engine)

conn = engine.connect()


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


def get_materials(**kwargs) -> list[Material]:
    pass


def get_free_materials() -> list[Material]:
    pass


def get_completed_materials() -> list[Material]:
    pass


def get_status(**kwargs) -> list[Status]:
    pass


def add_materials(materials: list[dict]) -> None:
    pass


def complete_material(*,
                      material_id: int) -> None:
    pass
