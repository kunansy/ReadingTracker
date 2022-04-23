import datetime
from uuid import UUID

import sqlalchemy.sql as sa
from sqlalchemy.engine import RowMapping

from tracker.common import database, models
from tracker.common.log import logger


async def get_material_titles() -> dict[UUID, str]:
    logger.debug("Getting material titles")

    stmt = sa.select([models.Materials.c.material_id,
                      models.Materials.c.title])

    async with database.session() as ses:
        return {
            row.material_id: row.title
            async for row in await ses.stream(stmt)
        }


async def get_notes() -> list[RowMapping]:
    logger.debug("Getting notes")
    stmt = sa.select(models.Notes)

    async with database.session() as ses:
        return (await ses.execute(stmt)).mappings().all()


async def get_notes_count(*,
                          material_id: UUID) -> int:
    stmt = sa.select(sa.func.count(1)) \
        .select_from(models.Notes) \
        .where(models.Notes.c.material_id == str(material_id))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def add_note(*,
                   material_id: UUID,
                   content: str,
                   chapter: int,
                   page: int,
                   date: datetime.date | None = None) -> None:
    date = date or database.today()
    logger.debug("Adding note for material_id=%s at %s",
                 material_id, date)

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

    logger.debug("Note_id=%s added", note_id)


async def get_note(*,
                   note_id: UUID) -> RowMapping | None:
    logger.debug("Getting note_id=%s", note_id)

    stmt = sa.select(models.Notes) \
        .where(models.Notes.c.note_id == str(note_id))

    async with database.session() as ses:
        return (await ses.execute(stmt)).mappings().one_or_none()


async def update_note(*,
                      note_id: UUID,
                      content: str,
                      page: int,
                      chapter: int) -> None:
    logger.debug("Updating note_id=%s", note_id)

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

    logger.debug("Note_id=%s updated", note_id)
