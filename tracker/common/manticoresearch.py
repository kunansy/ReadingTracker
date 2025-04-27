import datetime
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

import aiomysql
import sqlalchemy.sql as sa
from aiomysql.cursors import Cursor as MysqlCursor

from tracker.common import database, settings
from tracker.common.logger import logger
from tracker.common.schemas import CustomBaseModel
from tracker.models import models


class ManticoreException(Exception):
    pass


class Note(CustomBaseModel):
    note_id: UUID
    content: str
    added_at: datetime.datetime


class SearchResult(CustomBaseModel):
    replace_substring: str
    snippet: str


INSERT_QUERY = "INSERT INTO notes (note_id, content, added_at) VALUES (%s,%s,%s)"
DELETE_QUERY = "DELETE FROM notes WHERE note_id=%s"

# search works only with `text` fields
CREATE_TABLE_QUERY = """CREATE TABLE IF NOT EXISTS notes (
    note_id string,
    content text,
    added_at timestamp) morphology='lemmatize_ru_all, lemmatize_en_all'
"""


@asynccontextmanager
async def _cursor() -> AsyncGenerator[MysqlCursor]:
    new_session = await aiomysql.connect(
        host=settings.MANTICORE_MYSQL_HOST,
        port=settings.MANTICORE_MYSQL_PORT,
        db=settings.MANTICORE_MYSQL_DB_NAME,
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
    return sa.select(
        models.Notes.c.note_id,
        models.Notes.c.content,
        models.Notes.c.added_at,
    ).where(~models.Notes.c.is_deleted)


async def _get_notes() -> list[Note]:
    logger.debug("Getting all notes")
    stmt = _get_note_stmt()

    async with database.session() as ses:
        notes = [
            Note.model_validate(row, from_attributes=True)
            for row in (await ses.execute(stmt)).all()
        ]

    logger.debug("%s notes got", len(notes))
    return notes


async def _get_note(*, note_id: UUID) -> Note:
    logger.debug("Getting note=%s", note_id)

    stmt = _get_note_stmt().where(models.Notes.c.note_id == note_id)

    async with database.session() as ses:
        if note := (await ses.execute(stmt)).one_or_none():
            logger.debug("Note got")
            return Note.model_validate(note, from_attributes=True)

    logger.exception("Note=%s not found", note_id)
    raise ValueError(f"Note {note_id} not found")


async def _drop_table() -> None:
    query = "DROP TABLE IF EXISTS notes"

    async with _cursor() as cur:
        await cur.execute(query)


async def _create_table() -> None:
    async with _cursor() as cur:
        await cur.execute(CREATE_TABLE_QUERY)


async def _insert_all(notes: list[Note]) -> None:
    logger.debug("Inserting all %s notes", len(notes))
    if not notes:
        return

    async with _cursor() as cur:
        await cur.executemany(
            INSERT_QUERY,
            (list(note.model_dump().values()) for note in notes),
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
    await _insert_all(notes)
    logger.debug("Notes inserted")

    logger.info("Manticore search init completed")


async def delete(note_id: UUID | str) -> None:
    logger.debug("Deleting note=%s", note_id)

    async with _cursor() as cur:
        await cur.execute(DELETE_QUERY, note_id)

    logger.debug("Note deleted")


async def update_content(
    *,
    note_id: UUID | str,
    content: str,
    added_at: datetime.datetime,
) -> None:
    logger.debug("Updating note=%s", note_id)

    # because SQL updating don't work, replace don't delete the old doc
    async with _cursor() as cur:
        await cur.execute(DELETE_QUERY, note_id)
        await cur.execute(INSERT_QUERY, (note_id, content, added_at))

    logger.debug("Note updated")


def _get_search_query() -> str:
    # the first highlight is the string which will
    # be replaced by the found highlighted snippet;
    # snippet_separator is a symbol around match
    return """
    SELECT
        note_id,
        HIGHLIGHT({snippet_separator='',before_match='',after_match=''}),
        HIGHLIGHT({snippet_separator='',before_match='**',after_match='**'})
    FROM notes
    WHERE match(%s)
    ORDER BY weight() DESC
    """


async def search(query: str) -> dict[UUID, SearchResult]:
    logger.debug("Searching notes like: %r", query)
    if not query:
        return {}

    db_query = _get_search_query()

    async with _cursor() as cur:
        await cur.execute(db_query, query)
        results = {
            UUID(uid): SearchResult(replace_substring=repl, snippet=snippet)
            for uid, repl, snippet in await cur.fetchall()
        }

    logger.debug("%s match notes found", len(results))
    return results


async def autocompletion(*, query: str, limit: int = 5) -> list[str]:
    logger.debug("Searching autocompletions for: '%s'", query)

    db_query = f"""
    SELECT
       HIGHLIGHT({{snippet_separator='',before_match='**',after_match='**'}})
       FROM notes WHERE MATCH('@content {query}* ') ORDER BY WEIGHT() DESC LIMIT %s
   """  # noqa: S608

    async with _cursor() as cur:
        await cur.execute(db_query, limit)
        autocompletions = [row[0] for row in await cur.fetchall()]

    logger.debug("%s autocompletions found", len(autocompletions))
    return autocompletions


async def readiness() -> bool:
    query = "SHOW STATUS like 'uptime'"

    try:
        async with _cursor() as cur:
            await cur.execute(query)
            _, uptime = await cur.fetchone()
    except Exception as e:
        logger.warning("Fail checking ManticoreSearch readiness: %r", e)
        return False
    else:
        return uptime.isdigit() and int(uptime) >= 5  # noqa: PLR2004
