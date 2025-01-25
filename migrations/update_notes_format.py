import asyncio
import re
from uuid import UUID

from tracker.common.logger import logger
from tracker.notes import (
    db as notes_db,
    schemas,
)


def _delete_tags(text: str, tags: set[str]) -> str:
    for tag in tags:
        text = re.sub(notes_db._TAG_PATTERN.format(tag=tag), "", text)  # noqa: SLF001
    return text


def _delete_link(text: str, link_id: str | UUID | None) -> str:
    if not link_id:
        return text

    return text.replace(f"[[{link_id}]]", "")


def _dereplace_new_lines(string: str) -> str:
    return re.sub(r"<br/?>", "\n", string)


def add_dot(string: str) -> str:
    if not string or string.endswith((".", "?", "!")):
        return string
    return f"{string}."


def _format_content(content: str, tags: set[str], link_id: UUID | None) -> str:
    content = _delete_link(content, link_id)
    content = _delete_tags(content, tags)
    content = _dereplace_new_lines(content).strip()

    if content.endswith(("?", "!", ".")):
        end = content[-1]
        content = content.removesuffix(end).strip()

    return add_dot(content)


async def get_all_notes() -> list[notes_db.Note]:
    logger.info("Getting all notes...")
    return await notes_db.get_notes()


def format_content(note: notes_db.Note) -> str:
    content = schemas.demark_note(_format_content(note.content, note.tags, note.link_id))
    if "#" in note.content and len(note.tags) != note.content.count("#"):
        logger.warning(
            "Might be an error when deleting tags: note_id=%s, tags=%s, content=%s",
            note.note_id,
            note.tags,
            repr(note.content),
        )
        logger.warning("Clean content: %s", repr(content))

    return content


async def update_note(note: notes_db.Note) -> None:
    await notes_db.update_note(
        note_id=note.note_id,
        material_id=str(note.material_id),
        link_id=note.link_id,
        title=note.title,
        content=format_content(note),
        page=note.page,
        chapter=note.chapter,
        tags=list(note.tags),
    )


async def main() -> None:
    notes = await get_all_notes()

    for note in notes:
        await update_note(note)


if __name__ == "__main__":
    asyncio.run(main())
