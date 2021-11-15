import datetime
from typing import Optional
from uuid import UUID

import sqlalchemy.sql as sa
from sqlalchemy.engine import RowMapping

from tracker.common import database, models
from tracker.common.log import logger


async def get_material_titles() -> dict[UUID, str]:
    return await database.get_material_titles()


async def get_notes(*,
                    materials_ids: Optional[list[int]] = None) -> list[RowMapping]:
    how_many = 'all'
    if materials_ids:
        how_many = str(len(materials_ids))

    logger.debug("Getting notes for %s materials", how_many)

    stmt = sa.select(models.Notes)
    if materials_ids:
        stmt = stmt.where(models.Notes.c.material_id.in_(materials_ids))

    async with database.session() as ses:
        return (await ses.execute(stmt)).mappings().all()


async def add_note(*,
                   material_id: UUID,
                   content: str,
                   chapter: int,
                   page: int,
                   date: Optional[datetime.date] = None) -> None:
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
