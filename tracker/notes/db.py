import datetime
from collections import defaultdict
from uuid import UUID

import sqlalchemy.sql as sa

from tracker.common import database
from tracker.common.log import logger
from tracker.common.schemas import CustomBaseModel
from tracker.models import models, enums


class Note(CustomBaseModel):
    note_id: str
    material_id: str
    content: str
    added_at: datetime.datetime
    chapter: int
    page: int
    links: list[str]
    is_deleted: bool
    note_number: int


def get_distinct_chapters(notes: list[Note]) -> defaultdict[str, set[int]]:
    # chapters of the shown materials,
    #  it should help to create menu
    chapters = defaultdict(set)
    for note in notes:
        chapters[note.material_id].add(note.chapter)

    return chapters


async def get_material_type(*,
                            material_id: UUID | str) -> str | None:
    stmt = sa.select(models.Materials.c.material_type)\
        .where(models.Materials.c.material_id == str(material_id))

    async with database.session() as ses:
        if material_type := await ses.scalar(stmt):
            return material_type.name
    return None


@database.cache
async def get_material_types() -> dict[str, enums.MaterialTypesEnum]:
    stmt = sa.select([models.Materials.c.material_id,
                      models.Materials.c.material_type])

    async with database.session() as ses:
        return {
            str(material_id): material_type
            for material_id, material_type in await ses.execute(stmt)
        }


@database.cache
async def get_material_titles() -> dict[str, str]:
    logger.debug("Getting material titles")

    stmt = sa.select([models.Materials.c.material_id,
                      models.Materials.c.title])

    async with database.session() as ses:
        return {
            str(row.material_id): row.title
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
        .where(~models.Notes.c.is_deleted)\
        .order_by(models.Notes.c.note_number)

    async with database.session() as ses:
        return [
            Note(**row)
            for row in (await ses.execute(stmt)).mappings().all()
        ]


async def get_material_notes(*,
                             material_id: UUID | str) -> list[Note]:
    logger.debug("Getting material_id='%s' notes", material_id)

    stmt = sa.select(models.Notes) \
        .where(models.Notes.c.material_id == str(material_id))\
        .where(~models.Notes.c.is_deleted) \
        .order_by(models.Notes.c.note_number)

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


async def get_all_notes_count() -> dict[str, int]:
    logger.debug("Getting all notes count")

    stmt = sa.select([models.Notes.c.material_id.label('material_id'),
                      sa.func.count(1).label('count')]) \
        .select_from(models.Notes) \
        .group_by(models.Notes.c.material_id)

    async with database.session() as ses:
        return {
            str(material_id): count
            for material_id, count in (await ses.execute(stmt)).all()
        }


async def add_note(*,
                   material_id: UUID,
                   content: str,
                   chapter: int,
                   page: int,
                   tags: list[str],
                   links: list[str],
                   date: datetime.date | None = None) -> UUID:
    date = date or database.utcnow()
    logger.debug("Adding note for material_id='%s'", material_id)

    values = {
        'material_id': str(material_id),
        'content': content,
        'chapter': chapter,
        'page': page,
        'added_at': date,
        'tags': tags,
        'links': links
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
                      chapter: int,
                      tags: list[str],
                      links: list[str]) -> None:
    logger.debug("Updating note_id='%s'", note_id)

    values = {
        'content': content,
        'page': page,
        'chapter': chapter,
        'tags': tags,
        'links': links
    }
    stmt = models.Notes. \
        update().values(values) \
        .where(models.Notes.c.note_id == str(note_id))

    async with database.session() as ses:
        await ses.execute(stmt)

    logger.debug("Note_id='%s' updated", note_id)


async def delete_note(*,
                      note_id: UUID) -> None:
    logger.debug("Deleting note_id='%s'", note_id)

    values = {
        "is_deleted": True
    }
    stmt = models.Notes \
        .update().values(values) \
        .where(models.Notes.c.note_id == str(note_id))

    async with database.session() as ses:
        await ses.execute(stmt)

    logger.debug("Note_id='%s' deleted", note_id)


async def get_links() -> set[str]:
    stmt = sa.select(models.Notes.c.links)\
        .where(models.Notes.c.links != [])

    async with database.session() as ses:
        links: list[str] = sum([
            row[0]
            for row in (await ses.execute(stmt)).all()
        ], [])

    return set(links)
