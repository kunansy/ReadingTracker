from datetime import datetime
from typing import Optional

import sqlalchemy.sql as sa
from sqlalchemy.engine import RowMapping

from tracker.common import database, models
from tracker.common.log import logger
from tracker.notes import schemas


async def get_material_titles() -> dict[int, str]:
    return await database.get_material_titles()


async def get_notes(*,
                    materials_ids: Optional[list[int]] = None) -> list[RowMapping]:
    how_many = 'all'
    if materials_ids:
        how_many = len(materials_ids)

    logger.debug("Getting notes for %s materials", how_many)

    stmt = sa.select(models.Note)
    if materials_ids:
        stmt = stmt.where(models.Note.c.material_id.in_(materials_ids))

    async with database.session() as ses:
        return (await ses.execute(stmt)).mappings().all()


async def add_note(*,
                   note: schemas.Note,
                   date: Optional[datetime.date] = None) -> None:
    date = date or database.today()
    logger.debug("Adding note for material_id=%s at %s",
                 note.material_id, date)

    values = {
        'material_id': note.material_id,
        'content': note.content,
        'chapter': note.chapter,
        'page': note.page,
        'date': date
    }
    stmt = models.Note.\
        insert().values(values)\
        .returning(models.Note.c.id)

    async with database.session() as ses:
        note_id = await ses.execute(stmt)

    logger.debug("Note_id=%s added", note_id)
