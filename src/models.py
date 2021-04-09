from sqlalchemy import Column, ForeignKey, Integer, String, Date
from sqlalchemy.ext.declarative import declarative_base


DATE_FORMAT = '%d-%m-%Y'

Base = declarative_base()


class Material(Base):
    __tablename__ = 'material'

    material_id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    authors = Column(String, nullable=False)
    pages = Column(Integer, nullable=False)

    def __repr__(self) -> str:
        return "Material(" \
               f"{self.material_id}, {self.title}, " \
               f"{self.authors}, {self.pages})"


class Status(Base):
    __tablename__ = 'status'

    id = Column(Integer, primary_key=True)
    material_id = Column(Integer, ForeignKey('material.material_id'))
    begin = Column(Date)
    end = Column(Date)

    def __repr__(self) -> str:
        material_title = ...

        if begin := self.begin:
            begin = begin.strftime(DATE_FORMAT)
        if end := self.end:
            end = end.strftime(DATE_FORMAT)

        return "Status(" \
               f"{self.id}, {material_title}, " \
               f"{begin}, {end})"
