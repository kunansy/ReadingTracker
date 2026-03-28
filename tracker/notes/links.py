import asyncio
from typing import Any

from tracker.notes import cached, db


async def get_note_links(note: db.Note) -> dict[str, Any]:
    async with asyncio.TaskGroup() as tg:
        get_links_from_task = tg.create_task(db.get_links_from(note_id=note.note_id))
        if note.link_id:
            get_link_to_task = tg.create_task(cached.get_note(note.link_id))
        else:
            get_link_to_task = tg.create_task(asyncio.sleep(1 / 1000, result=None))

    return {"from": get_links_from_task.result(), "to": get_link_to_task.result()}
