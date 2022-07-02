import datetime
from typing import NamedTuple

import sqlalchemy.sql as sa

from tracker.common import database
from tracker.common.elasticsearch import AsyncElasticIndex
from tracker.common.log import logger
from tracker.models import models


class Note(NamedTuple):
    note_id: str
    material_id: str
    content: str
    added_at: datetime.datetime
    chapter: int
    page: int

    material_title: str
    material_authors: str
    material_type: str
    material_tags: str | None
    material_link: str | None


index = AsyncElasticIndex(Note)


def _get_note_stmt() -> sa.Select:
    return sa.select([models.Notes.c.note_id,
                      models.Notes.c.material_id,
                      models.Notes.c.content,
                      models.Notes.c.chapter,
                      models.Notes.c.page,
                      models.Notes.c.added_at,
                      models.Materials.c.title.label('material_title'),
                      models.Materials.c.authors.label('material_authors'),
                      models.Materials.c.material_type.label('material_type'),
                      models.Materials.c.tags.label('material_tags'),
                      models.Materials.c.link.label('material_link')]) \
        .join(models.Materials,
              models.Materials.c.material_id == models.Notes.c.material_id)


async def _get_notes() -> list[Note]:
    stmt = _get_note_stmt()

    async with database.session() as ses:
        return [
            Note(**row)
            for row in await ses.execute(stmt)
        ]


async def migrate_notes() -> None:
    logger.info('Migrating notes to Elasticsearch')

    logger.debug('Dropping index...')
    try:
        await index.drop_index()
    except Exception:
        logger.debug('Index does not exist')
    else:
        logger.debug('Index dropped')

    logger.debug('Creating index...')
    await index.create_index()
    logger.debug('Index created')

    logger.debug('Getting notes...')
    notes = await _get_notes()
    logger.debug('Got notes')

    logger.debug('Indexing notes...')
    for note in notes:
        await index.add(doc=note._asdict(), doc_id=note.note_id)
    logger.debug('Notes indexed')

    logger.info('Migrating notes completed')


async def find_notes(query: str) -> set[str]:
    notes = await index.multi_match(query=query)

    return {
        hint['_id']
        for hint in notes['hits']['hits']
    }
