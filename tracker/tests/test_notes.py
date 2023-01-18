import pytest
import sqlalchemy.sql as sa

from tracker.common import database
from tracker.models import models
from tracker.notes import db


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'material_id', (
        "5c66e1ca-eb52-47e5-af50-c48b345c7e6c",
        None,
    )
)
async def test_get_notes(material_id: str | None):
    print(material_id)
    notes = await db.get_notes(material_id=material_id)

    assert all(not note.is_deleted for note in notes), "Deleted note found"
    if material_id:
        assert all(note.material_id == material_id for note in notes), "Note with wrong material id found"

    stmt = sa.select(sa.func.count(1))\
        .select_from(models.Notes)\
        .where(~models.Notes.c.is_deleted)

    if material_id:
        stmt = stmt.where(models.Notes.c.material_id == material_id)

    async with database.session() as ses:
        notes_count = await ses.scalar(stmt)

    assert len(notes) == notes_count, f"Some notes missed, {len(notes)} != {len(notes_count)}"


@pytest.mark.asyncio
async def test_get_sorted_tags():
    material_id = "38e13f37-9d28-4c68-80b2-2bfdf6567372"
    material_tags = await db.get_tags(material_id=material_id)
    tags = await db.get_tags()

    test_result = await db.get_sorted_tags(material_id=material_id)

    assert len(tags) >= len(material_tags)
    assert len(tags) == len(test_result)

    assert sorted(test_result[:len(material_tags)]) == sorted(material_tags)