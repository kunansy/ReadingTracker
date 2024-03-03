from typing import Any
from uuid import UUID

import sqlalchemy.sql as sa

from tracker.common import database
from tracker.common.logger import logger
from tracker.models import models


async def notes_with_cards() -> list[UUID]:
    logger.info("Getting notes with a card")

    stmt = sa.select(models.Notes.c.note_id).join(
        models.Cards, models.Cards.c.note_id == models.Notes.c.note_id,
    )

    async with database.session() as ses:
        return await ses.scalars(stmt)  # type: ignore[return-value]


async def add_card(
    *, material_id: UUID, note_id: UUID, question: str, answer: str | None = None,
) -> None:
    logger.debug("Adding new card")

    values = {
        "material_id": str(material_id),
        "note_id": str(note_id),
        "question": question,
        "answer": answer,
    }
    stmt = models.Cards.insert().values(values)

    async with database.session() as ses:
        await ses.execute(stmt)

    logger.debug("Card added")


async def get_cards_list() -> list[dict[str, Any]]:
    logger.info("Getting all cards")

    stmt = (
        sa.select(models.Cards, models.Notes, models.Materials.c.title)
        .join(models.Notes, models.Cards.c.note_id == models.Notes.c.note_id)
        .join(
            models.Materials,
            models.Notes.c.material_id == models.Materials.c.material_id,
        )
    )

    async with database.session() as ses:
        return [
            {
                "card": {
                    "card_id": row.card_id,
                    "question": row.question,
                    "answer": row.answer,
                    "added_at": row.added_at,
                },
                "note": {
                    "note_id": row.note_id,
                    "material_title": row.title,
                    "content": row.content,
                    "page": row.page,
                    "chapter": row.chapter,
                },
            }
            async for row in await ses.stream(stmt)
        ]


async def get_cards_count() -> int:
    logger.debug("Getting amount of cards")

    stmt = sa.select(sa.func.count(1)).select_from(models.Cards)  # type: ignore[arg-type]

    async with database.session() as ses:
        return await ses.scalar(stmt) or 0
