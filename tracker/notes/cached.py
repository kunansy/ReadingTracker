from uuid import UUID

from tracker.common import redis_api
from tracker.notes import db


async def is_deleted(note_id: UUID | str) -> bool:
    if note := await redis_api.get_note(note_id, "is_deleted"):
        return note["is_deleted"]

    return await db.is_deleted(note_id=str(note_id))

