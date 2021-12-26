import asyncio
import datetime
import sqlite3
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, NamedTuple
from uuid import UUID

import ujson
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.ddl import DropTable

from tracker.common import models, settings


engine = create_async_engine(settings.DB_URI, encoding='utf-8')
sqlite_engine = sqlite3.connect("data/materials.db")
sqlite_engine.row_factory = sqlite3.Row


MAP = dict[int, UUID]


class Material(NamedTuple):
    material_id: int
    title: str
    authors: str
    pages: int
    tags: str


class Status(NamedTuple):
    status_id: int
    material_id: int
    begin: str
    end: str


class Note(NamedTuple):
    id: int
    content: str
    material_id: int
    date: str
    chapter: int
    page: int


class Card(NamedTuple):
    card_id: int
    question: str
    answer: str
    date: str
    material_id: int
    note_id: int


@asynccontextmanager
async def session(**kwargs) -> AsyncGenerator[AsyncSession, None]:
    new_session = AsyncSession(**kwargs, bind=engine, expire_on_commit=False)
    try:
        yield new_session
        await new_session.commit()
    except Exception:
        print("Error with the session")

        await new_session.rollback()
        raise
    finally:
        await new_session.close()


def _select_materials() -> list[Material]:
    stmt = "select * from material;"
    return [
        Material(**{k: v for k, v in zip(row.keys(), row)})
        for row in sqlite_engine.execute(stmt).fetchall()
    ]


def _select_statuses() -> list[Status]:
    stmt = "select * from status;"
    return [
        Status(**{k: v for k, v in zip(row.keys(), row)})
        for row in sqlite_engine.execute(stmt).fetchall()
    ]


def _select_notes() -> list[Note]:
    stmt = "select * from note;"
    return [
        Note(**{k: v for k, v in zip(row.keys(), row)})
        for row in sqlite_engine.execute(stmt).fetchall()
    ]


def _select_cards() -> list[Card]:
    stmt = "select * from card;"
    return [
        Card(**{k: v for k, v in zip(row.keys(), row)})
        for row in sqlite_engine.execute(stmt).fetchall()
    ]


async def _migrate_materials() -> MAP:
    ids: dict[int, UUID] = {}

    values = []
    for material in _select_materials():
        material_id = uuid.uuid4()
        ids[material.material_id] = material_id

        values += [{
            "material_id": str(material_id),
            "title": material.title,
            "authors": material.authors,
            "pages": material.pages,
            "tags": material.tags
        }]

    stmt = models.Materials \
        .insert().values(values)
    async with session() as ses:
        await ses.execute(stmt)

    return ids


async def _migrate_statuses(*,
                            material_ids: MAP) -> None:
    values = []
    for status in _select_statuses():
        value = {
            "material_id": str(material_ids[status.material_id]),
            "started_at": datetime.datetime.strptime(status.begin, '%Y-%m-%d').date(),
            "completed_at": None
        }
        if status.end:
            value["completed_at"] = datetime.datetime.strptime(status.end, '%Y-%m-%d').date()
        values += [value]

    stmt = models.Statuses \
        .insert().values(values)
    async with session() as ses:
        await ses.execute(stmt)


async def _migrate_notes(*,
                         material_ids: MAP) -> MAP:
    ids: dict[int, UUID] = {}

    values = []
    for note in _select_notes():
        note_id = uuid.uuid4()
        ids[note.id] = note_id

        values += [{
            "note_id": str(note_id),
            "content": note.content,
            "material_id": str(material_ids[note.material_id]),
            "added_at": datetime.datetime.strptime(note.date, '%Y-%m-%d').date(),
            "chapter": note.chapter,
            "page": note.page,
        }]

    stmt = models.Notes \
        .insert().values(values)
    async with session() as ses:
        await ses.execute(stmt)

    return ids


async def _migrate_cards(*,
                         material_ids: MAP,
                         note_ids: MAP) -> None:
    for card in _select_cards():
        values = {
            "note_id": str(note_ids[card.note_id]),
            "material_id": str(material_ids[card.material_id]),
            "question": card.question,
            "answer": card.answer,
            "added_at": datetime.datetime.strptime(card.date, '%Y-%m-%d').date(),
        }

        stmt = models.Cards \
            .insert().values(values)
        async with session() as ses:
            await ses.execute(stmt)


async def _migrate_reading_log(*,
                               material_ids: MAP) -> None:
    with open('data/log.json') as f:
        logs = ujson.load(f)

    values = [
        {
            "date": datetime.datetime.strptime(date, '%d-%m-%Y').date(),
            "count": info['count'],
            "material_id": str(material_ids[info['material_id']])
        }
        for date, info in logs.items()
    ]
    stmt = models.ReadingLog \
        .insert().values(values)

    async with session() as ses:
        await ses.execute(stmt)


async def migrate():
    material_ids = await _migrate_materials()
    await _migrate_statuses(material_ids=material_ids)
    note_ids = await _migrate_notes(material_ids=material_ids)
    await _migrate_cards(note_ids=note_ids, material_ids=material_ids)

    await _migrate_reading_log(material_ids=material_ids)


@compiles(DropTable, "postgresql")
def _compile_drop_table(element, compiler, **kwargs):
    return compiler.visit_drop_table(element) + " CASCADE"


async def recreate_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(models.metadata.drop_all)
        await conn.run_sync(models.metadata.create_all)


async def main() -> None:
    await recreate_db()
    await migrate()


if __name__ == '__main__':
    asyncio.run(main())
