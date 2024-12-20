from collections.abc import Callable, Iterable
from functools import wraps
from typing import Any, TypeAlias
from uuid import UUID

import aiokeydb

from tracker.common import logger, settings
from tracker.notes.db import Note


_NOTES_STORAGE = 0

DB: TypeAlias = aiokeydb.AsyncKeyDB  # noqa: UP040
FUNC_TYPE = Callable[[int], DB]


def cache(func: FUNC_TYPE) -> FUNC_TYPE:
    clients: dict[int, DB] = {}

    @wraps(func)
    def wrapped(db: int, *args: Any, **kwargs: Any) -> DB:
        nonlocal clients

        if db not in clients:
            clients[db] = func(db, *args, **kwargs)

        return clients[db]

    return wrapped


@cache
def client(db: int) -> DB:
    return aiokeydb.from_url(
        settings.CACHE_URL,
        password=settings.CACHE_PASSWORD,
        encoding="utf-8",
        decode_responses=True,
        db=db,
        protocol=3,
        _is_async=True,
    )


async def _set_dict(name: str, payload: dict, *, db: int) -> None:
    await client(db).hmset(name, payload)


async def _get_dict(name: str, fields: Iterable[str], *, db: int) -> list:
    return await client(db).hmget(name, fields)


async def _delete_dict(name: str, *, db: int) -> None:
    await client(db).delete(name)


async def set_notes(notes: list[Note]) -> None:
    for note in notes:
        await _set_dict(
            str(note.note_id),
            note.model_dump(mode="json", exclude_none=True),
            db=_NOTES_STORAGE,
        )


async def healthcheck() -> bool:
    try:
        return await client(_NOTES_STORAGE).ping()
    except Exception as e:
        logger.warning("Fail checking KeyDB readiness: %r", e)
        return False


async def get_note(note_id: UUID | str, *fields: str) -> dict | None:
    try:
        result = await _get_dict(str(note_id), fields, db=_NOTES_STORAGE)
    except aiokeydb.exceptions.ConnectionError:
        return None

    if not any(result):
        return None

    return dict(zip(fields, result, strict=False))


async def set_note(note: Note | dict) -> None:
    if isinstance(note, Note):
        note_dict = note.model_dump(mode="json", exclude_none=True)
    else:
        note_dict = note

    note_id = note_dict["note_id"]

    await _set_dict(note_id, note_dict, db=_NOTES_STORAGE)


async def delete_note(note_id: UUID | str) -> None:
    await _delete_dict(str(note_id), db=_NOTES_STORAGE)
