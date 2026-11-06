import datetime
from uuid import UUID

import sqlalchemy.sql as sa
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.cards import db as cards_db
from tracker.common import sort_keys
from tracker.common.pagination import Order, PageParams
from tracker.materials import db as materials_db
from tracker.models import enums, models
from tracker.notes import db as notes_db
from tracker.reading_log import db as logs_db


async def _row(ses: AsyncSession, table: sa.Table, id_column: str, row_id: UUID):
    stmt = sa.select(table).where(table.c[id_column] == str(row_id))
    return (await ses.execute(stmt)).one()


async def _any_note(ses: AsyncSession):
    return (await ses.execute(sa.select(models.Notes).limit(1))).one()


async def test_insert_material_sort_key(shared_session):
    material_id = await materials_db.insert_material(
        title="Sort key material",
        authors="Author",
        pages=10,
        material_type=enums.MaterialTypesEnum.book,
        tags=None,
        link=None,
    )

    row = await _row(shared_session, models.Materials, "material_id", material_id)
    assert row.sort_key == sort_keys.material_sort_key(
        added_at=row.added_at,
        material_id=material_id,
    )


async def test_insert_card_sort_key(shared_session):
    note = await _any_note(shared_session)

    card_id = await cards_db.add_card(
        material_id=note.material_id,
        note_id=note.note_id,
        question="Sort key question",
    )

    row = await _row(shared_session, models.Cards, "card_id", card_id)
    assert row.sort_key == sort_keys.card_sort_key(added_at=row.added_at, card_id=card_id)

    page = await cards_db.get_cards_page(
        material_id=None,
        params=PageParams(page_size=1, order=Order.DESC),
    )
    assert [card.card_id for card in page.items] == [card_id]


async def test_insert_log_record_sort_key(shared_session):
    note = await _any_note(shared_session)
    date = datetime.date(2100, 1, 1)

    log_id = await logs_db.insert_log_record(
        material_id=note.material_id,
        count=1,
        date=date,
    )

    row = await _row(shared_session, models.ReadingLog, "log_id", log_id)
    assert row.sort_key == sort_keys.reading_log_sort_key(
        material_id=row.material_id,
        date=date,
        log_id=log_id,
    )

    page = await logs_db.list_log_records_page(
        material_id=None,
        params=PageParams(page_size=1, order=Order.DESC),
    )
    assert [log.log_id for log in page.items] == [log_id]


async def test_insert_note_sort_key(shared_session):
    material = await _any_note(shared_session)

    note_id = await notes_db.insert_note(
        material_id=material.material_id,
        link_id=None,
        title=None,
        content="Sort key note",
        chapter="Chapter 9999999999",
        page=123,
        tags=[],
    )

    row = await _row(shared_session, models.Notes, "note_id", note_id)
    assert row.sort_key == sort_keys.note_sort_key(
        material_id=material.material_id,
        chapter="Chapter 9999999999",
        page=123,
        note_id=note_id,
    )
