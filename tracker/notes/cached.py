from uuid import UUID

from tracker.common import redis_api, settings
from tracker.notes import db


async def is_deleted(note_id: UUID | str) -> bool:
    if note := await redis_api.get_note(note_id, "is_deleted"):
        return note["is_deleted"]

    return await db.is_deleted(note_id=str(note_id))


async def get_note_json(note_id: UUID | str) -> dict | None:
    if note_ := await redis_api.get_note(note_id, *db.Note.model_fields.keys()):
        note = db.Note(**note_)
    elif note_ := await db.get_note(note_id=note_id):
        note = note_
    else:
        return None

    return note.model_dump() | {
        "added_at": note.added_at.strftime(settings.DATETIME_FORMAT),
    }
