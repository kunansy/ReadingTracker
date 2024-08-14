from uuid import UUID

from tracker.common import keydb_api
from tracker.notes import db


_ALL_NOTE_FIELDS = db.Note.model_fields.keys()
# TODO: add cache-miss metrics


async def is_deleted(note_id: UUID | str) -> bool:
    if note := await keydb_api.get_note(note_id, "is_deleted"):
        return note["is_deleted"]

    return await db.is_deleted(note_id=str(note_id))


async def get_note_json(note_id: UUID | str) -> db.Note | None:
    if note_ := await keydb_api.get_note(note_id, *_ALL_NOTE_FIELDS):
        return db.Note(**note_)
    if note := await db.get_note(note_id=note_id):
        return note
    return None


async def get_note(note_id: UUID | str) -> db.Note | None:
    if note := await keydb_api.get_note(note_id, *_ALL_NOTE_FIELDS):
        return db.Note(**note)

    return await db.get_note(note_id=note_id)
