import datetime
from uuid import UUID

import sqlalchemy.sql as sa

from tracker.common import database, pagination, sort_keys
from tracker.common.logger import logger
from tracker.common.schemas import CustomBaseModel
from tracker.models import enums, models


class Card(CustomBaseModel):
    card_id: UUID
    note_id: UUID
    material_id: UUID
    question: str
    answer: str | None
    added_at: datetime.datetime
    note_title: str | None
    note_content: str
    note_chapter: str
    note_page: int
    material_title: str
    material_authors: str
    material_type: enums.MaterialTypesEnum


async def get_notes_with_cards(*, material_id: UUID | None = None) -> set[UUID]:
    logger.info("Getting notes with cards")

    stmt = sa.select(models.Cards.c.note_id.distinct())

    if material_id:
        stmt = stmt.where(models.Cards.c.material_id == str(material_id))

    async with database.session() as ses:
        note_ids = await ses.scalars(stmt)

    return set(note_ids)


async def add_card(
    *,
    material_id: UUID,
    note_id: UUID,
    question: str,
    answer: str | None = None,
) -> UUID:
    logger.debug("Adding new card")

    card_id = models.generate_id()
    added_at = database.utcnow()
    values = {
        "card_id": card_id,
        "added_at": added_at,
        "sort_key": sort_keys.card_sort_key(added_at=added_at, card_id=card_id),
        "material_id": str(material_id),
        "note_id": str(note_id),
        "question": question,
        "answer": answer,
    }
    stmt = models.Cards.insert().values(values)

    async with database.session() as ses:
        result = await ses.execute(stmt)

    database.check_inserted_one(result, entity="Card")

    logger.debug("Card %r added", card_id)
    return UUID(card_id)


def _get_cards_stmt(
    *,
    note_id: UUID | None = None,
    material_id: UUID | str | None = None,
) -> sa.Select:
    stmt = (
        sa.select(
            models.Cards,
            models.Notes.c.title.label("note_title"),
            models.Notes.c.content.label("note_content"),
            models.Notes.c.chapter.label("note_chapter"),
            models.Notes.c.page.label("note_page"),
            models.Materials.c.authors.label("material_authors"),
            models.Materials.c.material_type,
            models.Materials.c.title.label("material_title"),
        )
        .join(models.Notes, models.Cards.c.note_id == models.Notes.c.note_id)
        .join(
            models.Materials,
            models.Notes.c.material_id == models.Materials.c.material_id,
        )
        .order_by(models.Cards.c.added_at.desc())
    )
    if note_id:
        stmt = stmt.where(models.Cards.c.note_id == str(note_id))
    if material_id:
        stmt = stmt.where(models.Cards.c.material_id == str(material_id))
    return stmt


async def get_cards(
    *,
    note_id: UUID | None = None,
    material_id: UUID | str | None = None,
) -> list[Card]:
    logger.info("Getting all cards")

    stmt = _get_cards_stmt(note_id=note_id, material_id=material_id)

    async with database.session() as ses:
        return [
            Card.model_validate(row, from_attributes=True)
            for row in (await ses.execute(stmt)).all()
        ]


async def get_cards_page(
    *,
    material_id: UUID | None,
    params: pagination.PageParams,
) -> pagination.Page[Card]:
    logger.info("Getting cards page")
    request = pagination.page_request(
        params,
        default_order=pagination.Order.DESC,
        material_id=material_id,
    )

    return await pagination.fetch_page(
        _get_cards_stmt(material_id=material_id),
        cursor_expr=pagination.cursor(models.Cards.c.sort_key),
        request=request,
        to_item=lambda row: Card.model_validate(row, from_attributes=True),
    )


async def get_all_cards_count() -> dict[UUID, int]:
    stmt = sa.select(
        models.Cards.c.material_id.label("material"),
        sa.func.count(1).label("cnt"),
    ).group_by(models.Cards.c.material_id)

    async with database.session() as ses:
        return {row.material: row.cnt for row in (await ses.execute(stmt)).all()}


async def get_cards_count(
    *,
    note_id: UUID | None = None,
    material_id: UUID | None = None,
) -> int:
    logger.debug("Getting amount of cards")

    stmt = sa.select(sa.func.count(1)).select_from(models.Cards)
    if note_id:
        stmt = stmt.where(models.Cards.c.note_id == str(note_id))
    if material_id:
        stmt = stmt.where(models.Cards.c.material_id == str(material_id))

    async with database.session() as ses:
        return await ses.scalar(stmt) or 0
