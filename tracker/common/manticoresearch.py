import datetime
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiomysql
import sqlalchemy.sql as sa
from aiomysql.cursors import Cursor as MysqlCursor
from pydantic import validator

from tracker.common import database, settings
from tracker.common.log import logger
from tracker.common.schemas import CustomBaseModel
from tracker.models import models


class ManticoreException(Exception):
    pass


class Note(CustomBaseModel):
    note_id: str
    material_id: str
    content: str
    added_at: datetime.datetime
    chapter: int
    page: int

    material_title: str
    material_authors: str
    material_type: str
    material_tags: str
    material_link: str

    @validator('content')
    def remove_tags_from_content(cls, content: str) -> str:
        """ Remove tags from note content to don't search on it """
        if (index := content.find('#')) == -1:
            return content

        return content[:index].strip()


INSERT_QUERY = "INSERT INTO notes (note_id, material_id, content, chapter, page, added_at, " \
               "material_title, material_authors, material_type, material_tags, material_link) "\
               "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"


@asynccontextmanager
async def _cursor() -> AsyncGenerator[MysqlCursor, None]:
    new_session = await aiomysql.connect(
        host=settings.MANTICORE_MYSQL_HOST,
        port=settings.MANTICORE_MYSQL_PORT,
        db=settings.MANTICORE_MYSQL_DB_NAME
    )

    try:
        async with new_session.cursor() as cur:
            yield cur
        await new_session.commit()
    except Exception as e:
        logger.exception("Manticore mysql error")

        await new_session.rollback()
        raise ManticoreException(e) from e
    finally:
        new_session.close()


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
                      sa.func.coalesce(models.Materials.c.tags, '').label('material_tags'),
                      sa.func.coalesce(models.Materials.c.link, '').label('material_link')]) \
        .join(models.Materials,
              models.Materials.c.material_id == models.Notes.c.material_id)\
        .where(~models.Notes.c.is_deleted)


async def _get_notes() -> list[Note]:
    logger.debug("Getting all notes")
    stmt = _get_note_stmt()

    async with database.session() as ses:
        notes = [
            Note(**row)
            for row in (await ses.execute(stmt)).mappings().all()
        ]

    logger.debug("%s notes got", len(notes))
    return notes


async def _get_note(*,
                    note_id: str) -> Note:
    logger.debug("Getting note=%s", note_id)

    stmt = _get_note_stmt() \
        .where(models.Notes.c.note_id == note_id)

    async with database.session() as ses:
        if note := (await ses.execute(stmt)).one_or_none():
            logger.debug("Note got")
            return Note(**note)

    logger.exception("Note=%s not found", note_id)
    raise ValueError(f'Note {note_id} not found')


async def _drop_table() -> None:
    query = "DROP TABLE IF EXISTS notes"

    async with _cursor() as cur:
        await cur.execute(query)


async def _create_table() -> None:
    # search works only with `text` fields
    query = """CREATE TABLE IF NOT EXISTS notes (
        note_id string,
        material_id string,
        content text,
        chapter int,
        page int,
        added_at timestamp,
        material_title string,
        material_authors string,
        material_type string,
        material_tags string,
        material_link string) morphology='lemmatize_ru_all, lemmatize_en_all'
    """

    async with _cursor() as cur:
        await cur.execute(query)


async def insert_all(notes: list[Note]) -> None:
    logger.debug("Inserting all %s notes", notes)
    if not notes:
        return None

    async with _cursor() as cur:
        await cur.executemany(
            INSERT_QUERY,
            (list(note.dict().values()) for note in notes)
        )

    logger.debug("Notes inserted")


async def init() -> None:
    logger.info("Init manticore search")

    logger.debug("Recreate tables")
    await _drop_table()
    await _create_table()
    logger.debug("Tables recreated")

    logger.debug("Getting notes")
    notes = await _get_notes()
    logger.debug("%s notes got, inserting", len(notes))
    await insert_all(notes)
    logger.debug("Notes inserted")

    logger.info("Manticore search init completed")


async def insert(note_id: str) -> None:
    logger.debug("Inserting note=%s", note_id)
    note = await _get_note(note_id=note_id)

    async with _cursor() as cur:
        await cur.execute(
            INSERT_QUERY,
            list(note.dict().values())
        )

    logger.debug("Note inserted")


async def delete(note_id: str) -> None:
    logger.debug("Deleting note=%s", note_id)

    query = "DELETE FROM notes WHERE note_id=%s"

    async with _cursor() as cur:
        await cur.execute(query, note_id)

    logger.debug("Note deleted")


async def update(note_id: str) -> None:
    logger.debug("Updating note=%s", note_id)

    await delete(note_id)
    await insert(note_id)

    logger.debug("Note updated")


async def search(query: str) -> set[str]:
    logger.debug("Searching notes like: '%s'", query)
    if not query:
        return set()

    db_query = "SELECT note_id FROM notes where match(%s) ORDER BY weight() DESC"
    async with _cursor() as cur:
        await cur.execute(db_query, query)
        note_ids = set(
            row[0]
            for row in await cur.fetchall()
        )

    logger.debug("%s match notes found", len(note_ids))
    return note_ids


async def readiness() -> bool:
    query = "SHOW STATUS like 'uptime'"

    async with _cursor() as cur:
        await cur.execute(query)
        _, uptime = await cur.fetchone()

    return uptime.isdigit() and int(uptime) >= 5
