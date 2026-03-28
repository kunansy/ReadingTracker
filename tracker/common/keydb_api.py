import contextlib
from collections.abc import Callable, Iterable
from functools import wraps
from typing import Any, cast
from urllib.parse import ParseResult, parse_qs, unquote, urlparse
from uuid import UUID

import redis.asyncio as redis
from redis.asyncio.connection import (
    URL_QUERY_ARGUMENT_PARSERS,
    ConnectKwargs,
)

from tracker.common import logger, settings
from tracker.notes.db import Note


_NOTES_STORAGE = 0

type DB = redis.Redis
type FUNC_TYPE = Callable[[int], DB]


def _parse_url(url: str) -> ConnectKwargs:  # noqa: C901
    parsed: ParseResult = urlparse(url)
    kwargs: dict[str, Any] = {}

    for name, value_list in parse_qs(parsed.query).items():
        if not (value_list and len(value_list) > 0):
            continue

        value = unquote(value_list[0])
        if not (parser := URL_QUERY_ARGUMENT_PARSERS.get(name)):
            kwargs[name] = value
            continue

        try:
            kwargs[name] = parser(value)
        except (TypeError, ValueError):
            raise ValueError(
                f"Invalid value for `{name}` in connection URL.",
            ) from None

    if parsed.username:
        kwargs["username"] = unquote(parsed.username)
    if parsed.password:
        kwargs["password"] = unquote(parsed.password)

    if parsed.scheme != "keydb":
        raise ValueError("KeyDB URL must specify only the keydb schema")

    if hostname := parsed.hostname:
        kwargs["host"] = unquote(hostname)
    if port := parsed.port:
        kwargs["port"] = int(port)

    # If there's a path argument, use it as the db argument if a
    # querystring value wasn't specified
    if parsed.path and "db" not in kwargs:
        with contextlib.suppress(AttributeError, ValueError):
            kwargs["db"] = int(unquote(parsed.path).replace("/", ""))

    return cast("ConnectKwargs", kwargs)


def cache(func: FUNC_TYPE) -> FUNC_TYPE:
    clients: dict[int, DB] = {}

    @wraps(func)
    def wrapped(db: int, *args: Any, **kwargs: Any) -> DB:
        nonlocal clients

        if db not in clients:
            clients[db] = func(db, *args, **kwargs)

        return clients[db]

    return wrapped


redis.connection.parse_url = _parse_url


@cache
def client(db: int) -> DB:
    return redis.Redis.from_url(
        settings.CACHE_URL,
        password=settings.CACHE_PASSWORD,
        encoding="utf-8",
        decode_responses=True,
        db=db,
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
    except redis.ConnectionError:
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
