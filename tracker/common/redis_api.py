from collections.abc import Iterable
from typing import TYPE_CHECKING
from uuid import UUID

from redis import asyncio as aioredis

from tracker.common import settings


if TYPE_CHECKING:
    import tracker.notes.db


_NOTES_STORAGE = 0


def client(db: int) -> aioredis.Redis:
    clients: dict[int, aioredis.Redis] = {}

    def wrapper() -> aioredis.Redis:
        nonlocal clients
        if db not in clients:
            client = aioredis.from_url(
                settings.CACHE_URL,
                password=settings.CACHE_PASSWORD,
                encoding="utf-8",
                decode_responses=True,
                db=db,
                protocol=3,
            )
            clients[db] = client

        return clients[db]

    return wrapper()


async def _set_dict(name: str, payload: dict, *, db: int) -> None:
    await client(db).hmset(name, payload)


async def _get_dict(name: str, fields: Iterable[str], *, db: int) -> list:
    return await client(db).hmget(name, fields)


async def set_notes(notes: list["tracker.notes.db.Note"]) -> None:
    for note in notes:
        await _set_dict(
            str(note.note_id),
            note.model_dump(mode="json", exclude_none=True),
            db=_NOTES_STORAGE,
        )


async def healthcheck() -> bool:
    return await client(_NOTES_STORAGE).ping()


async def get_note(note_id: UUID | str, *fields: str) -> dict | None:
    result = await _get_dict(str(note_id), fields, db=_NOTES_STORAGE)

    if not any(result):
        return None

    return dict(zip(fields, result, strict=False))
