import datetime
from collections import defaultdict
from typing import NamedTuple
from uuid import UUID

import sqlalchemy.sql as sa

from tracker.common import database
from tracker.models import models
from tracker.common.log import logger


class Note(NamedTuple):
    note_id: UUID
    material_id: UUID
    content: str
    added_at: datetime.datetime
    chapter: int
    page: int
    is_deleted: bool


def get_distinct_chapters(notes: list[Note]) -> defaultdict[UUID, set[int]]:
    # chapters of the shown materials,
    #  it should help to create menu
    chapters = defaultdict(set)
    for note in notes:
        chapters[note.material_id].add(note.chapter)

    return chapters


async def get_material_type(*,
                            material_id: UUID) -> str | None:
    stmt = sa.select(models.Materials.c.material_type)\
        .where(models.Materials.c.material_id == str(material_id))

    async with database.session() as ses:
        if material_type := await ses.scalar(stmt):
            return material_type.name
    return None


@database.cache
async def get_material_types() -> dict[UUID, str]:
    stmt = sa.select([models.Materials.c.material_id,
                      models.Materials.c.material_type])

    async with database.session() as ses:
        return {
            material_id: material_type
            for material_id, material_type in await ses.execute(stmt)
        }


@database.cache
async def get_material_titles() -> dict[UUID, str]:
    logger.debug("Getting material titles")

    stmt = sa.select([models.Materials.c.material_id,
                      models.Materials.c.title])

    async with database.session() as ses:
        return {
            row.material_id: row.title
            for row in (await ses.execute(stmt)).mappings().all()
        }


@database.cache
async def get_material_with_notes_titles() -> dict[str, str]:
    logger.debug("Getting material with note titles")

    stmt = sa.select([sa.text("distinct on (materials.material_id) materials.material_id"),
                      models.Materials.c.title])\
        .join(models.Notes,
              models.Notes.c.material_id == models.Materials.c.material_id)

    async with database.session() as ses:
        return {
            str(row.material_id): row.title
            for row in (await ses.execute(stmt)).mappings().all()
        }


async def get_notes() -> list[Note]:
    logger.debug("Getting all notes")

    stmt = sa.select(models.Notes)\
        .where(~models.Notes.c.is_deleted)

    async with database.session() as ses:
        return [
            Note(**row)
            for row in (await ses.execute(stmt)).mappings().all()
        ]


async def get_material_notes(*,
                             material_id: UUID) -> list[Note]:
    logger.debug("Getting material_id='%s' notes", material_id)

    stmt = sa.select(models.Notes) \
        .where(models.Notes.c.material_id == str(material_id))\
        .where(~models.Notes.c.is_deleted)

    async with database.session() as ses:
        return [
            Note(**row)
            for row in (await ses.execute(stmt)).mappings().all()
        ]


async def get_note(*,
                   note_id: UUID) -> Note | None:
    logger.debug("Getting note_id='%s'", note_id)

    stmt = sa.select(models.Notes) \
        .where(models.Notes.c.note_id == str(note_id)) \
        .where(~models.Notes.c.is_deleted)

    async with database.session() as ses:
        if note := (await ses.execute(stmt)).mappings().one_or_none():
            logger.debug("Note_id='%s' got", note_id)
            return Note(**note)

    logger.debug("Note_id='%s' not found", note_id)
    return None


async def get_all_notes_count() -> dict[UUID, int]:
    logger.debug("Getting all notes count")

    stmt = sa.select([models.Notes.c.material_id.label('material_id'),
                      sa.func.count(1).label('count')]) \
        .select_from(models.Notes) \
        .group_by(models.Notes.c.material_id)

    async with database.session() as ses:
        return {
            material_id: count
            for material_id, count in await ses.execute(stmt)
        }


async def add_note(*,
                   material_id: UUID,
                   content: str,
                   chapter: int,
                   page: int,
                   date: datetime.date | None = None) -> UUID:
    date = date or database.utcnow()
    logger.debug("Adding note for material_id='%s'", material_id)

    values = {
        'material_id': str(material_id),
        'content': content,
        'chapter': chapter,
        'page': page,
        'added_at': date
    }
    stmt = models.Notes.\
        insert().values(values)\
        .returning(models.Notes.c.note_id)

    async with database.session() as ses:
        note_id = (await ses.execute(stmt)).one()[0]

    logger.debug("Note_id='%s' added", note_id)
    return note_id


async def update_note(*,
                      note_id: UUID,
                      content: str,
                      page: int,
                      chapter: int) -> None:
    logger.debug("Updating note_id='%s'", note_id)

    values = {
        'content': content,
        'page': page,
        'chapter': chapter
    }
    stmt = models.Notes. \
        update().values(values) \
        .where(models.Notes.c.note_id == str(note_id))

    async with database.session() as ses:
        await ses.execute(stmt)

    logger.debug("Note_id='%s' updated", note_id)
