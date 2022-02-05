import datetime
from typing import Optional
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


async def add_note(*,
                   material_id: UUID,
                   content: str,
                   chapter: Optional[int],
                   page: Optional[int],
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
